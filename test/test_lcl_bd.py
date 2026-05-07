""" Local Detector Board Initial Confidence Check

To be run as part of commissioning a newly constructed board as a check on
connection and soldering integrity rather than functionality.

"""

from machine import Pin, I2C
from neopixel import NeoPixel
import time


# ADC1015 parameters to start read.
# 1st ADC is I2C address 72, 2nd 73
_ADC_CONF0 = b'\x95\xE3' # Single read, mux 1 (blk 1 or 3 differential), FSR 2048 mV, 3300 sps, comparator off
_ADC_CONF1 = b'\xA5\xE3' # as above mux 2 (blk 2 or 4 differential)
_ADC_CONF2 = b'\xB5\xE3' # as above mux 3 (differential but both on DCC-L so 0)
_ADC_CONF3 = b'\xE3\xE3' # mux 6 (single ended measurement of DCC-L wrt GND1), FSR 4096 mV
_ADC_CONF_ADD = 1
_adc_addr = {0:(72, _ADC_CONF0),
             1:(72, _ADC_CONF1),
             2:(73, _ADC_CONF0),
             3:(73, _ADC_CONF1),
             4:(72, _ADC_CONF2),
             5:(72, _ADC_CONF3),
             6:(73, _ADC_CONF2),
             7:(73, _ADC_CONF3)}



# pins used as inputs from detector
pins = [Pin(x, Pin.IN) for x in (14, 15, 16, 17, 18, 19, 20, 21, 27)]
# i2c pin numbers
i2c_pn = (4, 5, 6 ,7)

# PICO on board LED
led = Pin("LED", Pin.OUT)
# last neopixel in chain
np = NeoPixel(Pin(22), 5)
# user press button
sw = Pin(26, Pin.IN, Pin.PULL_UP)


np.fill((0, 0, 0))
np.write()

print()
print("RailCom Quad Local Detector Commissioning Tests")
print("Enter test function call at >>> prompt")

def scan_pins():
    """Scan RailCom detector Pins 

    Scan the GPIOs associated with the local RailCom detector outputs.

    RX data pins have even numbers. Orientation indication pins are odd numbers, but
    Pin 27 is DCC power on indication (low for true).
    
    As it happens with no DCC power connected
    even numbered pins should be '0'
    and odd numbered pins '1'.

    With DDC power but no load pin inputs are reversed.
    I.e. even numbered pins '1' and
    odd numbered pins '0'

    With DCC power and a significant load on one of the blocks(e.g. loco fitted with
    decoder other than Zimo) and assuming the DCC cut out is not in force
    at the sample time:
    - the relevent even pin should be '0' and
    - the relevent odd pin depends on the DCC phase at the time of the sample.

    Take multiple samples to ensure both '0' and '1' readings are seen on odd numbered pin.
    """

    for p in pins:
        print(p, p.value())



def scan_i2c():

    """
    I2C sca and scl pins should be high due to pull ups.
    
    With no DCC power connected
    I2C0 scan returns decimal 60 (OLED).
    I2C1 scan returns empty list [].
    
    With DDC power

    I2C0 scan returns decimal 60 (OLED).
    I2C1 scan returns decimal 72 & 74 (ADC).
    """

    for p in i2c_pn:
        pin = Pin(p, Pin.IN)
        print(pin, pin.value())


    # I2C0 scan should return decimal 60 (OLED)
    print("I2C0 scan:", I2C(0).scan())
    # I2C1 scan should return nothing with no DCC power
    # I2C1 scan should return decimal 72 & 74 with DCC power applied
    print("I2C1 scan:", I2C(1).scan())

def test_sw2():
    """check user button 

        Test the user button (SW2) and NeoPixel chain.
        Pico on board LED should show opposite of last Neopixel.
        If on board LED toggles with button, button is OK.
        If Neopixel doesn't toggle but LED does, Neopixel chain problem.

        Ctrl + C to exit.
    """
    try:
        while True:
            swv = sw.value()
            led.value(not swv)
            np.__setitem__(np.__len__() - 1, (swv * 20,0,0))
            np.write()
    except KeyboardInterrupt:
        print("SW 2 Test Exit")
        np.fill((0, 0, 0))
        np.write()
        led.value(0)

def test_DCC_sense():
    count = 0
    def _sense_isr(pin):
        nonlocal count
        if pin.value() == 0:
            # pin reverted back to DCC on - too short for cutout
            return
        # assumed cut out
        count += 1

    sense_pin = Pin(27, Pin.IN)
    sense_pin.irq(_sense_isr, Pin.IRQ_RISING, hard = True)
    time.sleep(10)
    sense_pin.irq(None)
    print("Cutout frequency:", count  / 10, "per sec.")





def test_adc():
    """Test ADC conversion
    
    This tests the raw DCC side ADC sampling as used for block occupancy.
    Nominally this is a differential reading of the voltage across the load sense
    1.8 ohm resistor.

    The sample is not timed wrt the DCC phasing or cut out and
    for a given load may vary in value and sign.
    Due to offset bias in the analogue circuitry
    the zero load reading will usually be non zero. 
    These factors are allowed for by taking multiple reads and filtering in the main application but not here!
    
    The no load reading should be in the range ±25 and for a given block will be more or less constant.
    The load for a 10K resistor in the range ±(50 - 150) after allowing for offset but lower values may occasionally be seen.
    The load for a decoder > ±1000 but this will depend on the decoder's quiescent current. Lower values may occasionally be seen.

    Readings 1 to 4 are block differential readings wrt DCC-L.
    5 and 7 are differential readings of DCC-L against itself. Should always be 0.
    6 and 8 are single ended readings of DCC-L wrt GND1. Should be c.1250 corresponding to 5/2 V.
    """

    def _adc2int(adc_res):
        # this is a 12 bit signed (2's comp) value but left aligned.  L.S 4 bits always 0
        value = (adc_res[0] << 4) + (adc_res[1] >> 4)
        if (adc_res[0] & 0x80) != 0:
            value = ((~value & 0x0fff) + 1) * -1
        return(value)
   
    for adc in sorted(_adc_addr.keys()):
        i2c_addr, conf = _adc_addr[adc]
        try:
            I2C(1).writeto_mem(i2c_addr,_ADC_CONF_ADD,conf) # start read
            while True:
                res = I2C(1).readfrom_mem(i2c_addr,_ADC_CONF_ADD, 2)
                if (res[0] & 0x80) != 0:
                    break   # we have a result
            value = _adc2int(I2C(1).readfrom_mem(i2c_addr, 0, 2))
            print(adc + 1, value)
                
        except OSError:
            # i2c error - no track power most likely
            print("Is DCC power on?")
            return
        

