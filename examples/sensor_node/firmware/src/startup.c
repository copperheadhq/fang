/*
 * Reset and the vector table for the STM32F401RE, with nothing the firmware
 * does not use: the core's sixteen exception vectors, of which SysTick is the
 * only one handled.
 */

#include <stdint.h>

extern uint32_t _estack;
extern uint32_t _sidata;
extern uint32_t _sdata;
extern uint32_t _edata;
extern uint32_t _sbss;
extern uint32_t _ebss;

int main(void);
void SysTick_Handler(void);

void Reset_Handler(void)
{
    uint32_t *source = &_sidata;
    for (uint32_t *destination = &_sdata; destination < &_edata;) {
        *destination++ = *source++;
    }
    for (uint32_t *destination = &_sbss; destination < &_ebss;) {
        *destination++ = 0;
    }
    main();
    for (;;) {
    }
}

void Default_Handler(void)
{
    for (;;) {
    }
}

__attribute__((section(".isr_vector"), used))
const void *const vector_table[16] = {
    &_estack,
    (const void *)Reset_Handler,
    (const void *)Default_Handler,      /* NMI */
    (const void *)Default_Handler,      /* HardFault */
    (const void *)Default_Handler,      /* MemManage */
    (const void *)Default_Handler,      /* BusFault */
    (const void *)Default_Handler,      /* UsageFault */
    0, 0, 0, 0,
    (const void *)Default_Handler,      /* SVCall */
    (const void *)Default_Handler,      /* DebugMonitor */
    0,
    (const void *)Default_Handler,      /* PendSV */
    (const void *)SysTick_Handler,
};
