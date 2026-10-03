/*
 * Firmware for the simavr runner's tests: an ATtiny84A program per rule the
 * runner keeps, each one build flag, and each the least that makes its rule
 * observable on PB2 (OC0A), the pin the tests' one-LED board observes. None
 * of it is a product. The flags are prefixed because avr/io.h names
 * registers and bits OSCCAL and PRTIM1.
 *
 *   -DFIX_BLINK      toggles PB2 every 2000 iterations of a 4-cycle loop
 *                    (1 ms at 8 MHz), the count read from a table in .data,
 *                    so the image carries a data segment the startup code
 *                    copies from flash
 *   -DFIX_PINS       Timer 0 toggles OC0A every 100 cycles while PB2 is still
 *                    an input; PB2 is made an output after 4000 cycles and an
 *                    input again after 4000 more
 *   -DFIX_PRESCALER  Timer 0 toggles OC0A every 256 cycles; after 100 000
 *                    cycles the firmware sets the clock prescaler to 1 by its
 *                    timed sequence (clock_prescale_set)
 *   -DFIX_LATE       the same, writing the division ten cycles after the
 *                    enable, which the part ignores
 *   -DFIX_OSCCAL     blinks, and writes the oscillator calibration register
 *                    after the first toggle
 *   -DFIX_PRTIM1     blinks, and sets only PRR's Timer/Counter1 bit
 *   -DFIX_HALT       drives PB2 high, then sleeps with interrupts off
 */

#include <avr/interrupt.h>
#include <avr/io.h>
#include <avr/power.h>
#include <avr/sleep.h>
#include <stdint.h>
#include <util/delay_basic.h>

#if defined(FIX_BLINK) || defined(FIX_OSCCAL) || defined(FIX_PRTIM1)
/* Not const: the table lives in .data, initialized from flash at reset. */
static volatile uint16_t half_period[2] = {2000, 2000};

int main(void)
{
	uint8_t toggles = 0;

	DDRB |= _BV(PB2);
#if defined(FIX_PRTIM1)
	PRR = _BV(PRTIM1);
#endif
	for (;;) {
		PORTB ^= _BV(PB2);
#if defined(FIX_OSCCAL)
		if (toggles == 1)
			OSCCAL = OSCCAL + 1;
#endif
		_delay_loop_2(half_period[toggles & 1]);
		toggles++;
	}
}

#elif defined(FIX_PINS)
int main(void)
{
	/* CTC, toggle OC0A on compare match, clk/1: a toggle every 100 cycles. */
	OCR0A = 99;
	TCCR0A = _BV(COM0A0) | _BV(WGM01);
	TCCR0B = _BV(CS00);
	_delay_loop_2(1000);
	DDRB |= _BV(PB2);
	_delay_loop_2(1000);
	DDRB &= (uint8_t)~_BV(PB2);
	for (;;)
		;
}

#elif defined(FIX_PRESCALER) || defined(FIX_LATE)
int main(void)
{
	DDRB |= _BV(PB2);
	/* CTC, toggle OC0A on compare match, clk/1: a toggle every 256 cycles. */
	OCR0A = 255;
	TCCR0A = _BV(COM0A0) | _BV(WGM01);
	TCCR0B = _BV(CS00);
	_delay_loop_2(25000);
#if defined(FIX_PRESCALER)
	clock_prescale_set(clock_div_1);
#else
	cli();
	CLKPR = _BV(CLKPCE);
	__asm__ volatile("nop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop");
	CLKPR = 0;
	sei();
#endif
	for (;;)
		;
}

#elif defined(FIX_HALT)
int main(void)
{
	DDRB |= _BV(PB2);
	PORTB |= _BV(PB2);
	set_sleep_mode(SLEEP_MODE_PWR_DOWN);
	sleep_enable();
	cli();
	sleep_cpu();
	for (;;)
		;
}

#else
#error "build with one of -DFIX_BLINK -DFIX_PINS -DFIX_PRESCALER -DFIX_LATE -DFIX_OSCCAL -DFIX_PRTIM1 -DFIX_HALT"
#endif
