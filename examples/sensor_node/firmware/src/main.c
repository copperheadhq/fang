/*
 * sensor_node firmware: an STM32F401RE reading an HS3001 over I2C1.
 *
 * Register-level C with no vendor HAL, so that every defect the suite needs is
 * one build flag away and every register the firmware writes is visible here.
 * The core runs from the 16 MHz HSI the part resets to; nothing configures the
 * PLL.
 *
 *   USART2 on PA2/PA3 (AF7) at 115200 baud: a boot line, then one
 *     "temp=<degC>" line per good reading, and "sensor absent" once each time
 *     the sensor stops answering.
 *   I2C1 on PB8/PB9 (AF4, open drain): the HS3001 at SENSOR_ADDRESS, asked for
 *     a measurement every 100 ms and read 40 ms later.
 *   PA5: the status LED, toggled every 500 ms while readings succeed and every
 *     100 ms while they fail.
 *
 * Defects, each a build flag:
 *   -DSENSOR_ADDRESS=0x45  talks to an address nobody answers on
 *   -DI2C_PUSH_PULL        leaves the I2C pins push-pull instead of open drain
 *   -DNO_TIMEOUT           waits for the sensor forever
 */

#include <stdint.h>

#ifndef SENSOR_ADDRESS
#define SENSOR_ADDRESS 0x44
#endif

#define REG(address) (*(volatile uint32_t *)(address))

#define RCC_AHB1ENR   REG(0x40023830)
#define RCC_APB1ENR   REG(0x40023840)

#define GPIOA_BASE    0x40020000u
#define GPIOB_BASE    0x40020400u
#define GPIO_MODER(p)   REG((p) + 0x00)
#define GPIO_OTYPER(p)  REG((p) + 0x04)
#define GPIO_OSPEEDR(p) REG((p) + 0x08)
#define GPIO_ODR(p)     REG((p) + 0x14)
#define GPIO_AFRL(p)    REG((p) + 0x20)
#define GPIO_AFRH(p)    REG((p) + 0x24)

#define USART2_SR     REG(0x40004400)
#define USART2_DR     REG(0x40004404)
#define USART2_BRR    REG(0x40004408)
#define USART2_CR1    REG(0x4000440C)

#define I2C1_CR1      REG(0x40005400)
#define I2C1_CR2      REG(0x40005404)
#define I2C1_DR       REG(0x40005410)
#define I2C1_SR1      REG(0x40005414)
#define I2C1_SR2      REG(0x40005418)
#define I2C1_CCR      REG(0x4000541C)
#define I2C1_TRISE    REG(0x40005420)

#define SYST_CSR      REG(0xE000E010)
#define SYST_RVR      REG(0xE000E014)
#define SYST_CVR      REG(0xE000E018)

#define CORE_HZ       16000000u

#define CR1_PE    (1u << 0)
#define CR1_START (1u << 8)
#define CR1_STOP  (1u << 9)
#define CR1_ACK   (1u << 10)

#define SR1_SB    (1u << 0)
#define SR1_ADDR  (1u << 1)
#define SR1_BTF   (1u << 2)
#define SR1_RXNE  (1u << 6)
#define SR1_AF    (1u << 10)

#define I2C_TIMEOUT_MS 5u

static volatile uint32_t ticks;

void SysTick_Handler(void)
{
    ticks++;
}

static void sleep_until_interrupt(void)
{
    __asm volatile ("wfi");
}

static void delay_ms(uint32_t ms)
{
    uint32_t start = ticks;
    while ((uint32_t)(ticks - start) < ms) {
        sleep_until_interrupt();
    }
}

/* ---- the console ------------------------------------------------------ */

static void uart_putc(char c)
{
    while (!(USART2_SR & (1u << 7))) {
    }
    USART2_DR = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

static void uart_put_centi(int32_t centi)
{
    char digits[12];
    int n = 0;
    uint32_t magnitude;

    if (centi < 0) {
        uart_putc('-');
        magnitude = (uint32_t)(-centi);
    } else {
        magnitude = (uint32_t)centi;
    }
    uint32_t whole = magnitude / 100u;
    uint32_t fraction = magnitude % 100u;
    do {
        digits[n++] = (char)('0' + whole % 10u);
        whole /= 10u;
    } while (whole && n < (int)sizeof digits);
    while (n) {
        uart_putc(digits[--n]);
    }
    uart_putc('.');
    uart_putc((char)('0' + fraction / 10u));
    uart_putc((char)('0' + fraction % 10u));
}

/* ---- I2C1 --------------------------------------------------------------- */

/* Waits for a flag in SR1. A negative acknowledgement or a timeout ends the
   wait; without the timeout, a sensor that never answers hangs the firmware,
   which is the defect NO_TIMEOUT builds on purpose. */
static int i2c_wait(uint32_t flag)
{
#ifdef NO_TIMEOUT
    while (!(I2C1_SR1 & flag)) {
    }
    return 0;
#else
    uint32_t start = ticks;
    for (;;) {
        uint32_t sr1 = I2C1_SR1;
        if (sr1 & flag) {
            return 0;
        }
        if (sr1 & SR1_AF) {
            I2C1_SR1 = ~SR1_AF;
            return -1;
        }
        if ((uint32_t)(ticks - start) > I2C_TIMEOUT_MS) {
            return -2;
        }
    }
#endif
}

static void i2c_stop(void)
{
    I2C1_CR1 |= CR1_STOP;
}

static int i2c_address(uint8_t address, int read)
{
    I2C1_CR1 |= CR1_START;
    if (i2c_wait(SR1_SB)) {
        i2c_stop();
        return -1;
    }
    I2C1_DR = (uint32_t)((address << 1) | (read ? 1u : 0u));
    if (i2c_wait(SR1_ADDR)) {
        i2c_stop();
        return -1;
    }
    (void)I2C1_SR2;     /* reading SR1 then SR2 clears ADDR */
    return 0;
}

/* The HS3001's measurement request: its address with the write bit and no
   data (HS300x datasheet, measurement request). */
static int hs3001_request(void)
{
    if (i2c_address(SENSOR_ADDRESS, 0)) {
        return -1;
    }
    i2c_stop();
    return 0;
}

/* Reads n >= 3 bytes with the reference-manual sequence for a master
   receiver: the last three bytes are handled around BTF so that NACK and STOP
   land on the right byte. */
static int i2c_read(uint8_t address, uint8_t *buffer, int n)
{
    I2C1_CR1 |= CR1_ACK;
    if (i2c_address(address, 1)) {
        return -1;
    }
    int i = 0;
    while (n - i > 3) {
        if (i2c_wait(SR1_RXNE)) {
            i2c_stop();
            return -1;
        }
        buffer[i++] = (uint8_t)I2C1_DR;
    }
    if (i2c_wait(SR1_BTF)) {
        i2c_stop();
        return -1;
    }
    I2C1_CR1 &= ~CR1_ACK;
    buffer[i++] = (uint8_t)I2C1_DR;
    if (i2c_wait(SR1_BTF)) {
        i2c_stop();
        return -1;
    }
    i2c_stop();
    buffer[i++] = (uint8_t)I2C1_DR;
    if (i2c_wait(SR1_RXNE)) {
        return -1;
    }
    buffer[i++] = (uint8_t)I2C1_DR;
    return 0;
}

/* One reading in hundredths of a degree Celsius. The HS3001's temperature is
   the upper 14 bits of bytes 2 and 3: T = raw / (2^14 - 1) * 165 - 40. */
static int read_temperature(int32_t *centi)
{
    uint8_t data[4];

    if (hs3001_request()) {
        return -1;
    }
    delay_ms(40);
    if (i2c_read(SENSOR_ADDRESS, data, 4)) {
        return -1;
    }
    if ((data[0] >> 6) != 0) {
        return -1;      /* stale or invalid status */
    }
    uint32_t raw = ((uint32_t)data[2] << 6) | ((uint32_t)data[3] >> 2);
    *centi = (int32_t)((raw * 16500u + 8191u) / 16383u) - 4000;
    return 0;
}

/* ---- set-up ------------------------------------------------------------- */

static void configure(void)
{
    RCC_AHB1ENR |= (1u << 0) | (1u << 1);           /* GPIOA, GPIOB */
    RCC_APB1ENR |= (1u << 17) | (1u << 21);         /* USART2, I2C1 */

    /* PA5: push-pull output, the status LED. */
    GPIO_MODER(GPIOA_BASE) = (GPIO_MODER(GPIOA_BASE) & ~(3u << 10)) | (1u << 10);

    /* PA2, PA3: USART2 TX and RX at AF7. */
    GPIO_MODER(GPIOA_BASE) = (GPIO_MODER(GPIOA_BASE) & ~((3u << 4) | (3u << 6)))
                             | (2u << 4) | (2u << 6);
    GPIO_AFRL(GPIOA_BASE) = (GPIO_AFRL(GPIOA_BASE) & ~((0xFu << 8) | (0xFu << 12)))
                            | (7u << 8) | (7u << 12);

    /* PB8, PB9: I2C1 SCL and SDA at AF4, open drain unless the push-pull
       defect is built. The board carries the pull-ups. */
    GPIO_MODER(GPIOB_BASE) = (GPIO_MODER(GPIOB_BASE) & ~((3u << 16) | (3u << 18)))
                             | (2u << 16) | (2u << 18);
#ifndef I2C_PUSH_PULL
    GPIO_OTYPER(GPIOB_BASE) |= (1u << 8) | (1u << 9);
#endif
    GPIO_OSPEEDR(GPIOB_BASE) |= (3u << 16) | (3u << 18);
    GPIO_AFRH(GPIOB_BASE) = (GPIO_AFRH(GPIOB_BASE) & ~((0xFu << 0) | (0xFu << 4)))
                            | (4u << 0) | (4u << 4);

    /* USART2: 115200 baud from 16 MHz, transmitter on. */
    USART2_BRR = (CORE_HZ + 115200u / 2u) / 115200u;
    USART2_CR1 = (1u << 13) | (1u << 3);

    /* I2C1: standard mode, 100 kHz from a 16 MHz APB1. */
    I2C1_CR1 = 0;
    I2C1_CR2 = 16u;
    I2C1_CCR = 80u;
    I2C1_TRISE = 17u;
    I2C1_CR1 = CR1_PE;

    /* SysTick: a 1 ms tick from the core clock. */
    SYST_RVR = CORE_HZ / 1000u - 1u;
    SYST_CVR = 0;
    SYST_CSR = 7u;
}

int main(void)
{
    configure();
    uart_puts("sensor_node boot\r\n");

    uint32_t next_sample = 0;
    uint32_t next_toggle = 500;
    int reading_ok = 0;
    int reported_absent = 0;

    for (;;) {
        if ((int32_t)(ticks - next_sample) >= 0) {
            next_sample = ticks + 100u;
            int32_t centi;
            if (read_temperature(&centi) == 0) {
                reading_ok = 1;
                reported_absent = 0;
                uart_puts("temp=");
                uart_put_centi(centi);
                uart_puts("\r\n");
            } else {
                reading_ok = 0;
                if (!reported_absent) {
                    uart_puts("sensor absent\r\n");
                    reported_absent = 1;
                }
            }
        }
        if ((int32_t)(ticks - next_toggle) >= 0) {
            next_toggle = ticks + (reading_ok ? 500u : 100u);
            GPIO_ODR(GPIOA_BASE) ^= (1u << 5);
        }
        sleep_until_interrupt();
    }
}
