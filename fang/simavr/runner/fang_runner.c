/*
 * fang_runner.c -- runs AVR firmware in simavr for fang, and records what the
 * board would see it do.
 *
 * Part of fang, under its Apache-2.0 licence. simavr is GPL-3.0-or-later: fang
 * ships this file as source, the host builds it against the simavr installed
 * there, and fang neither links simavr nor distributes a binary linked
 * against it (copperhead RFC 12, Sections 4.2 and 4.4).
 *
 * Spec: "The Emulator Script Carries Only What The Lowering Writes",
 * "Observation Comes From Probes, Not From The Firmware's Report", "Fuses Set
 * An AVR Part's Clock And Are Stated" and "Registers An Engine Does Not Model
 * Are Watched".
 *
 *   fang-runner run.cfg
 *
 * The configuration holds only lines the lowering writes (fang/simavr/
 * lowering.py), each a keyword of the fixed set below and its arguments, and
 * anything else is refused before the core is made. The run is bounded by
 * virtual time, kept in segments so that a change of the clock prescaler
 * changes how many nanoseconds a cycle is from that cycle on. The events are
 * written one JSON object per line, as fang.events/v1 has them:
 *
 *   run.start      at 0
 *   gpio.edge      {level} on an observed pin while it is an output: its level
 *                  when it becomes one, and each change after
 *   gpio.release   {} when an observed pin stops being an output
 *   clock.change   {prescaler} when a CLKPR write takes effect
 *   model.warning  {text} for a watched register written, and for every
 *                  error or warning simavr logs
 *   run.end        {reason} at the run's bound ("completed"), or where the
 *                  core halted first ("halted"); a crash writes none
 *
 * Exit status: 0 when run.end was written, 2 for a configuration refused,
 * 3 for a crash, 4 for firmware that cannot be loaded.
 */

/* srandom() is POSIX, which a strict C99 build hides. */
#define _DEFAULT_SOURCE 1

#include <inttypes.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "avr_ioport.h"
#include "sim_avr.h"
#include "sim_io.h"
#include "sim_irq.h"

#define MAX_PINS 32
#define MAX_WATCHES 16
#define MAX_TEXT 512

/* -- the configuration ---------------------------------------------------- */

struct pin {
	char source[129];
	char port;
	int index;
	int driven;        /* the pin is an output */
	int recorded;      /* the level last recorded, or -1 for none or released */
	avr_irq_t *irq;
};

struct watch {
	char name[17];
	unsigned address;
	unsigned mask;
	int every_write;
	avr_io_write_t inner;
	void *inner_param;
};

static struct {
	char mcu[33];
	uint64_t oscillator_hz;
	unsigned prescaler;
	unsigned prescaler_register;
	uint64_t seed;
	uint64_t run_until_ns;
	char flash[129];
	char events[129];
	char target[129];
	struct pin pins[MAX_PINS];
	int npins;
	struct watch watches[MAX_WATCHES];
	int nwatches;
} cfg;

static void refuse(int line, const char *why)
{
	fprintf(stderr, "fang-runner: run.cfg line %d: %s\n", line, why);
	exit(2);
}

/* An identifier the events carry unescaped: what the lowering validated,
 * checked again, since this is the side of the boundary that writes JSON. */
static int identifier(const char *s, size_t max)
{
	size_t n = strlen(s);
	if (n == 0 || n > max)
		return 0;
	for (size_t i = 0; i < n; i++) {
		char c = s[i];
		int ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
			(c >= '0' && c <= '9') || c == '_' || c == '.' || c == ':' || c == '-';
		if (!ok)
			return 0;
	}
	return 1;
}

/* A file of the bundle: a name, never a path. */
static int file_name(const char *s)
{
	return identifier(s, 128) && !strchr(s, ':') && strcmp(s, ".") && strcmp(s, "..");
}

static int number(const char *s, uint64_t *out)
{
	char *end;
	if (!*s || *s == '-')
		return 0;
	unsigned long long v = strtoull(s, &end, 0);
	if (*end)
		return 0;
	*out = v;
	return 1;
}

static void read_configuration(const char *path)
{
	FILE *f = fopen(path, "r");
	if (!f) {
		fprintf(stderr, "fang-runner: cannot read %s\n", path);
		exit(2);
	}
	char text[512];
	int line = 0, seen = 0;
	enum { MCU = 1, OSC = 2, PRESCALER = 4, REGISTER = 8, SEED = 16, UNTIL = 32,
	       FLASH = 64, EVENTS = 128, TARGET = 256 };
	while (fgets(text, sizeof text, f)) {
		line++;
		size_t n = strlen(text);
		if (n && text[n - 1] == '\n')
			text[--n] = 0;
		else if (!feof(f))
			refuse(line, "a line longer than the lowering writes");
		char *word[6] = {0};
		int words = 0;
		for (char *tok = strtok(text, " "); tok; tok = strtok(NULL, " ")) {
			if (words == 6)
				refuse(line, "more arguments than any keyword takes");
			word[words++] = tok;
		}
		if (line == 1) {
			if (words != 2 || strcmp(word[0], "fang-simavr-run") || strcmp(word[1], "1"))
				refuse(line, "not a fang-simavr-run 1 configuration");
			continue;
		}
		if (words == 0)
			refuse(line, "an empty line");
		uint64_t v;
#define ONCE(bit) do { if (seen & (bit)) refuse(line, "a keyword given twice"); seen |= (bit); } while (0)
		if (!strcmp(word[0], "mcu") && words == 2 && identifier(word[1], 32)) {
			ONCE(MCU);
			strcpy(cfg.mcu, word[1]);
		} else if (!strcmp(word[0], "oscillator_hz") && words == 2 && number(word[1], &v) && v) {
			ONCE(OSC);
			cfg.oscillator_hz = v;
		} else if (!strcmp(word[0], "prescaler") && words == 2 && number(word[1], &v) &&
			   v && v <= 256 && !(v & (v - 1))) {
			ONCE(PRESCALER);
			cfg.prescaler = (unsigned)v;
		} else if (!strcmp(word[0], "prescaler_register") && words == 2 && number(word[1], &v) &&
			   v >= 0x20 && v <= 0xFF) {
			ONCE(REGISTER);
			cfg.prescaler_register = (unsigned)v;
		} else if (!strcmp(word[0], "seed") && words == 2 && number(word[1], &v)) {
			ONCE(SEED);
			cfg.seed = v;
		} else if (!strcmp(word[0], "run_until_ns") && words == 2 && number(word[1], &v) && v) {
			ONCE(UNTIL);
			cfg.run_until_ns = v;
		} else if (!strcmp(word[0], "flash") && words == 2 && file_name(word[1])) {
			ONCE(FLASH);
			strcpy(cfg.flash, word[1]);
		} else if (!strcmp(word[0], "events") && words == 2 && file_name(word[1])) {
			ONCE(EVENTS);
			strcpy(cfg.events, word[1]);
		} else if (!strcmp(word[0], "target") && words == 2 && identifier(word[1], 128)) {
			ONCE(TARGET);
			strcpy(cfg.target, word[1]);
		} else if (!strcmp(word[0], "pin") && words == 4 && identifier(word[1], 128) &&
			   strlen(word[2]) == 1 && word[2][0] >= 'A' && word[2][0] <= 'Z' &&
			   number(word[3], &v) && v <= 7) {
			if (cfg.npins == MAX_PINS)
				refuse(line, "more pins than the runner observes");
			for (int i = 0; i < cfg.npins; i++)
				if (!strcmp(cfg.pins[i].source, word[1]))
					refuse(line, "a signal observed twice");
			struct pin *p = &cfg.pins[cfg.npins++];
			strcpy(p->source, word[1]);
			p->port = word[2][0];
			p->index = (int)v;
			p->recorded = -1;
		} else if (!strcmp(word[0], "watch") && words == 5 && identifier(word[1], 16)) {
			uint64_t address, mask;
			if (!number(word[2], &address) || address < 0x20 || address > 0xFF ||
			    !number(word[3], &mask) || !mask || mask > 0xFF ||
			    (strcmp(word[4], "write") && strcmp(word[4], "set")))
				refuse(line, "a watch the lowering does not write");
			if (cfg.nwatches == MAX_WATCHES)
				refuse(line, "more watches than the runner keeps");
			struct watch *w = &cfg.watches[cfg.nwatches++];
			strcpy(w->name, word[1]);
			w->address = (unsigned)address;
			w->mask = (unsigned)mask;
			w->every_write = !strcmp(word[4], "write");
		} else {
			refuse(line, "not a line of the fixed set");
		}
#undef ONCE
	}
	fclose(f);
	if (line == 0)
		refuse(1, "an empty configuration");
	unsigned required = MCU | OSC | PRESCALER | REGISTER | SEED | UNTIL | FLASH | EVENTS | TARGET;
	if ((seen & required) != required)
		refuse(line, "a required keyword is missing");
}

/* -- events and time -------------------------------------------------------- */

static avr_t *avr;
static FILE *events;
static uint64_t seq;
static uint64_t segment_cycle, segment_ns;
static unsigned divisor;

/* Virtual time at a cycle: the segment's start, and the cycles since at the
 * segment's prescaler. Floored, in 128-bit arithmetic: an 8 MHz cycle is
 * 125 ns exactly, a 128 kHz one 7812.5. */
static uint64_t now_ns(avr_cycle_count_t cycle)
{
	unsigned __int128 elapsed = (unsigned __int128)(cycle - segment_cycle) * divisor * 1000000000u;
	return segment_ns + (uint64_t)(elapsed / cfg.oscillator_hz);
}

static void json_text(FILE *f, const char *s)
{
	fputc('"', f);
	for (; *s; s++) {
		unsigned char c = (unsigned char)*s;
		if (c == '"' || c == '\\')
			fprintf(f, "\\%c", c);
		else if (c == '\n')
			fputs("\\n", f);
		else if (c == '\t')
			fputs("\\t", f);
		else if (c < 0x20 || c >= 0x7F)
			fprintf(f, "\\u%04x", c);
		else
			fputc(c, f);
	}
	fputc('"', f);
}

/* One event, unless it falls at or after the run's bound, which run.end
 * marks: nothing after it was observed. `payload` is JSON already. */
static void record(uint64_t t, const char *source, const char *type, const char *payload)
{
	if (!events || t >= cfg.run_until_ns)
		return;
	fprintf(events, "{\"seq\":%" PRIu64 ",\"t_ns\":%" PRIu64 ",\"source\":\"%s\",\"type\":\"%s\",\"payload\":%s}\n",
		seq++, t, source, type, payload);
}

static void warn(const char *text)
{
	if (!events)
		return;
	uint64_t t = now_ns(avr->cycle);
	if (t >= cfg.run_until_ns)
		return;
	fprintf(events, "{\"seq\":%" PRIu64 ",\"t_ns\":%" PRIu64 ",\"source\":\"%s\",\"type\":\"model.warning\",\"payload\":{\"text\":",
		seq++, t, cfg.target);
	json_text(events, text);
	fputs("}}\n", events);
}

/* simavr's log: errors and warnings are the model saying it met something it
 * does not model, and are recorded as such; everything is kept in the log. */
static void logger(avr_t *from, const int level, const char *format, va_list ap)
{
	(void)from;
	if (level > LOG_WARNING)
		return;
	char text[MAX_TEXT];
	vsnprintf(text, sizeof text, format, ap);
	size_t n = strlen(text);
	while (n && (text[n - 1] == '\n' || text[n - 1] == '\r'))
		text[--n] = 0;
	fprintf(stderr, "%s\n", text);
	if (level >= LOG_ERROR && avr)
		warn(text);
}

/* -- pins ---------------------------------------------------------------------- */

static void edge(struct pin *p, int level)
{
	if (p->recorded == level)
		return;
	p->recorded = level;
	record(now_ns(avr->cycle), p->source, "gpio.edge", level ? "{\"level\":1}" : "{\"level\":0}");
}

/* The pin's level, from the port or a timer's compare output, both of which
 * simavr raises on the pin's IRQ whatever its direction. It reaches the pin
 * only while the pin is an output, as on the part. */
static void on_level(struct avr_irq_t *irq, uint32_t value, void *param)
{
	(void)irq;
	struct pin *p = param;
	if (p->driven)
		edge(p, value & 1);
}

static void on_direction(struct avr_irq_t *irq, uint32_t value, void *param)
{
	(void)irq;
	char port = *(char *)param;
	for (int i = 0; i < cfg.npins; i++) {
		struct pin *p = &cfg.pins[i];
		if (p->port != port)
			continue;
		int output = (value >> p->index) & 1;
		if (output && !p->driven) {
			p->driven = 1;
			edge(p, p->irq->value & 1);
		} else if (!output && p->driven) {
			p->driven = 0;
			p->recorded = -1;
			record(now_ns(avr->cycle), p->source, "gpio.release", "{}");
		}
	}
}

/* -- the clock prescaler ---------------------------------------------------- */

static int prescaler_window;           /* CLKPCE written, the change still open */
static avr_cycle_count_t prescaler_enabled;
static unsigned clkps;

static unsigned log2u(unsigned v)
{
	unsigned n = 0;
	while (v >>= 1)
		n++;
	return n;
}

static int window_open(void)
{
	return prescaler_window && avr->cycle - prescaler_enabled <= 4;
}

/* CLKPR, as DS40002269A section 6.5.2 has it: CLKPCE written to one with the
 * other bits zero opens a four-cycle window, and CLKPS written with CLKPCE
 * zero inside it takes effect; any other write changes nothing. simavr does
 * not model the register, so it is modelled here and the time base moves. */
static void on_prescaler(struct avr_t *a, avr_io_addr_t addr, uint8_t v, void *param)
{
	(void)a;
	(void)addr;
	(void)param;
	if (v == 0x80) {
		prescaler_window = 1;
		prescaler_enabled = avr->cycle;
		return;
	}
	if ((v & 0x80) || !window_open())
		return;
	prescaler_window = 0;
	unsigned select = v & 0x0F;
	if (select > 8) {
		char text[MAX_TEXT];
		snprintf(text, sizeof text, "CLKPR written 0x%02X: a reserved clock division", v);
		warn(text);
		return;
	}
	segment_ns = now_ns(avr->cycle);
	segment_cycle = avr->cycle;
	clkps = select;
	divisor = 1u << select;
	avr->frequency = (uint32_t)(cfg.oscillator_hz / divisor);
	char payload[64];
	snprintf(payload, sizeof payload, "{\"prescaler\":%u}", divisor);
	record(segment_ns, cfg.target, "clock.change", payload);
}

static uint8_t read_prescaler(struct avr_t *a, avr_io_addr_t addr, void *param)
{
	(void)a;
	(void)addr;
	(void)param;
	return (uint8_t)((window_open() ? 0x80 : 0) | clkps);
}

/* -- watched registers ---------------------------------------------------------- */

static void on_watched(struct avr_t *a, avr_io_addr_t addr, uint8_t v, void *param)
{
	struct watch *w = param;
	if (w->every_write || (v & w->mask)) {
		char text[MAX_TEXT];
		if (w->every_write)
			snprintf(text, sizeof text, "%s written 0x%02X: the model does not model it", w->name, v);
		else
			snprintf(text, sizeof text, "%s written 0x%02X: bits 0x%02X are not modelled",
				 w->name, v, v & w->mask);
		warn(text);
	}
	if (w->inner)
		w->inner(a, addr, v, w->inner_param);
	else
		a->data[addr] = v;
}

/* simavr shares at most four I/O registers between write hooks and its cores
 * use them, so a watched register's handler is wrapped, not joined. */
static void hook_write(unsigned address, avr_io_write_t c, struct watch *w)
{
	avr_io_addr_t io = AVR_DATA_TO_IO(address);
	w->inner = avr->io[io].w.c;
	w->inner_param = avr->io[io].w.param;
	avr->io[io].w.c = c;
	avr->io[io].w.param = w;
}

/* -- the run ---------------------------------------------------------------------- */

static uint8_t *read_flash(const char *name, uint32_t *size)
{
	FILE *f = fopen(name, "rb");
	if (!f) {
		fprintf(stderr, "fang-runner: cannot read %s\n", name);
		exit(4);
	}
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	fseek(f, 0, SEEK_SET);
	uint8_t *data = malloc(n > 0 ? (size_t)n : 1);
	if (!data || n <= 0 || fread(data, 1, (size_t)n, f) != (size_t)n) {
		fprintf(stderr, "fang-runner: %s is empty or unreadable\n", name);
		exit(4);
	}
	fclose(f);
	*size = (uint32_t)n;
	return data;
}

/* The serial number simavr draws from the process at avr_init, made the
 * seed's instead: splitmix64, so two seeds differ in every byte. */
static void fix_serial(uint64_t seed)
{
	uint64_t z = seed + 0x9E3779B97F4A7C15ull;
	for (size_t i = 0; i < sizeof avr->serial; i++) {
		z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
		z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
		z ^= z >> 31;
		avr->serial[i] = (uint8_t)z;
	}
	/* Into the log, which the run keeps: the evidence that it was the seed's. */
	fprintf(stderr, "fang-runner: serial");
	for (size_t i = 0; i < sizeof avr->serial; i++)
		fprintf(stderr, " %02x", avr->serial[i]);
	fprintf(stderr, " from seed %" PRIu64 "\n", seed);
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: fang-runner run.cfg\n");
		return 2;
	}
	read_configuration(argv[1]);

	/* The seed first, before anything simavr draws. */
	srandom((unsigned)cfg.seed);
	avr_global_logger_set(logger);

	avr = avr_make_mcu_by_name(cfg.mcu);
	if (!avr) {
		fprintf(stderr, "fang-runner: simavr has no core %s\n", cfg.mcu);
		return 2;
	}
	avr_init(avr);
	fix_serial(cfg.seed);
	divisor = cfg.prescaler;
	clkps = log2u(divisor);
	avr->frequency = (uint32_t)(cfg.oscillator_hz / divisor);
	avr->log = LOG_WARNING;

	uint32_t size;
	uint8_t *flash = read_flash(cfg.flash, &size);
	if (size > (uint32_t)avr->flashend + 1) {
		fprintf(stderr, "fang-runner: %s is %u bytes, past the core's flash\n", cfg.flash, size);
		return 4;
	}
	avr_loadcode(avr, flash, size, 0);
	free(flash);

	events = fopen(cfg.events, "w");
	if (!events) {
		fprintf(stderr, "fang-runner: cannot write %s\n", cfg.events);
		return 4;
	}
	/* Line-buffered, so a run ended by its wall-clock limit keeps what it saw. */
	setvbuf(events, NULL, _IOLBF, 0);

	static char ports[MAX_PINS];
	int nports = 0;
	for (int i = 0; i < cfg.npins; i++) {
		struct pin *p = &cfg.pins[i];
		p->irq = avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ(p->port), p->index);
		if (!p->irq) {
			fprintf(stderr, "fang-runner: %s has no pin %c%d\n", cfg.mcu, p->port, p->index);
			return 2;
		}
		avr_irq_register_notify(p->irq, on_level, p);
		if (!memchr(ports, p->port, (size_t)nports))
			ports[nports++] = p->port;
	}
	for (int i = 0; i < nports; i++)
		avr_irq_register_notify(
			avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ(ports[i]), IOPORT_IRQ_DIRECTION_ALL),
			on_direction, &ports[i]);

	static struct watch prescaler_hook;
	hook_write(cfg.prescaler_register, on_prescaler, &prescaler_hook);
	avr_register_io_read(avr, cfg.prescaler_register, read_prescaler, NULL);
	for (int i = 0; i < cfg.nwatches; i++)
		hook_write(cfg.watches[i].address, on_watched, &cfg.watches[i]);

	record(0, "", "run.start", "{}");
	int state = cpu_Running;
	while (now_ns(avr->cycle) < cfg.run_until_ns) {
		state = avr_run(avr);
		if (state == cpu_Done || state == cpu_Crashed)
			break;
	}
	if (state == cpu_Crashed) {
		fprintf(stderr, "fang-runner: the core crashed at %" PRIu64 " ns\n", now_ns(avr->cycle));
		fclose(events);
		return 3;
	}
	if (state == cpu_Done) {
		/* simavr takes a core asleep with interrupts off for the end of the
		 * program and stops; the part would sit there. Either way nothing
		 * after this was observed, so the run has not completed. */
		uint64_t t = now_ns(avr->cycle);
		if (t < cfg.run_until_ns) {
			fprintf(events, "{\"seq\":%" PRIu64 ",\"t_ns\":%" PRIu64 ",\"source\":\"\",\"type\":\"run.end\",\"payload\":{\"reason\":\"halted\"}}\n",
				seq++, t);
			fclose(events);
			return 0;
		}
	}
	fprintf(events, "{\"seq\":%" PRIu64 ",\"t_ns\":%" PRIu64 ",\"source\":\"\",\"type\":\"run.end\",\"payload\":{\"reason\":\"completed\"}}\n",
		seq++, cfg.run_until_ns);
	fclose(events);
	return 0;
}
