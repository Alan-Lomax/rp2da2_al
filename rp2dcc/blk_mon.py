"""DCC Block Current Detection
    :author: Paul Redhead

This module contains the functions and classes for DCC block detection
based on current load monitoring. This is for the resistor based detector where the
ADC is on the track side of the galvanic isolation and uses a TI ADC1015 ADC rather than the
Pico's own ADC.
"""
"""        Copyright (C) 2023, 2024, 2025, 2026 Paul Redhead

        This program is free software: you can redistribute it and/or modify it
        under the terms of the GNU General Public License as published by the Free Software Foundation, 
        either version 3 of the License, or (at your option) any later version.
        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
        See the GNU General Public License for more details.
        You should have received a copy of the GNU General Public License along with this program.
        If not, see <http://www.gnu.org/licenses/>.
"""
import asyncio

from micropython import const

from machine import I2C

from device import Device

_TIMER_PERIOD = const(50)   # time in ms between checks for current load on block

_LULU_SIZE = const(7) # size of LULU filter buffer


# The characteristic time constant for a simple infinite impulse response digital
# filter is 𝞃 = -1/ln(d) where d is the filter ratio.
# A ratio of 0.8 
# in conjuntion with a 50 ms periodgives a characteristic time of c. 0.22s for
# signal filter.
# This is equivalent to the CR time constant of a simple analogue low pass filter.
_FILTER_FACTOR = const(5)   # IIR filter factor (reading)
_FILTER_RATIO =  const((_FILTER_FACTOR - 1) / _FILTER_FACTOR)

# In conjuntion with a 50 ms period this gives a characteristic time of c. 5s for
# zero reference filter.
_Z_FILTER_FACTOR = const(100)   # IIR filter factor (zero offset)
_Z_FILTER_RATIO =  const((_Z_FILTER_FACTOR - 1) / _Z_FILTER_FACTOR)

_U_THRESHOLD = const(150) # 
_L_THRESHOLD = const(75) #

# ADC1015 parameters to start read.
# 
_ADC_CONF0 = b'\x95\xE3' # Single read, mux 1, FSR 2048 mV, 3300 sps, comparator off
_ADC_CONF1 = b'\xA5\xE3' # as above but mux 2
_ADC_CONF_ADD = const(1)
_adc_addr = {0: (72, _ADC_CONF0), 1:(72, _ADC_CONF1), 2: (73, _ADC_CONF0), 3:(73, _ADC_CONF1)}
_i2c = I2C(1)


class DCCBlkDet(Device):
    """DCC (block current) Detector
    
    This runs on a local block detector MCU.

    In addition to interpreting channel 1 messages elsewhere, we monitor
    the block for occupancy, detecting non RailCom decoders and other loads.
    E.g coaches with lighting etc. This detection uses the same raw hardware
    detection as the RailCom channel 1 detector, but the signal is processed
    differently within the detector hardware and interpreted differently
    here.

    The RailCom output from the detector is a digital signal, whereas this
    uses an analog output from the detector.
    
    The detected current is amplified within the detector such that 1mA of
    track current appears at the analog input as cf * gain mV where cf is
    the track current to detector conversion factor (2.2) and gain (100) is the
    gain of the detector op. amp. This equates to 1mA => 220 mV.  The signal
    is centred around a nominal 0V.
    
    The op. amp. runs on 3.3 V and its outputs will saturate at about ± 8mA 
    of input current. If using resistor wheel sets, a typical value is 10 kΩ
    and thresholds can be set at c. 1mA to detect these.

    This inherits from the Device Class.

    Block status may be:
        - empty
        - occupied
        - unknown (start of day)

    Attributes:
        DEVICE_TYPE: 'd' for (current) detector
    """

    DEVICE_TYPE = const('d')


    _i2c_lock = asyncio.Lock() # to ensure only one read at a time

    def __init__(self, blk_name, adc, led):
        """Construct the block current detector
        
        This constructs the block current detector.

        The base Device class is initiated with the block name and type.
        Inititial values are set.

        args:
            blk_name: the name of the block
            adc: logical number of the adc
        """

        self._id_val = {} # channel 1 payload values for ids 1 & 2
        self._adc = adc #
        self._led = led
        # set up readings buffer for LULU filter
        self._readings = [0 for _ in range(_LULU_SIZE - 1)]
        self._av = 0.0 # initialise average IIR filtered reading with start value
        self._offset = 0.0 

        """block state may be unknown, empty, occupied"""
        self._blk_state = Device.UNKNOWN # start of day value
       
        self._ready_flag = asyncio.ThreadSafeFlag() # used to signal new state available to comms agent

        super().__init__(blk_name,
                        DCCBlkDet.DEVICE_TYPE)
        
        asyncio.create_task(self._monitor())

    async def wait_for_flag(self):
        """ Wait for the new state available event

        This waits for the asynchio event to be set.
        """
        await self._ready_flag.wait()
        return
    
    def report_event(self, event, data):
        """ Report Event
        
        This overrides the Device.report_event method.
        It sets the event flag to indicate block status change.
        
        args:
            event:  updated Block status code.
            data:   a tuple containing address type, address & orientation  
        """
        self._led.update(event, data)
        self._ready_flag.set()
        super().report_event(event, data)

    def get_sensor_state(self):
        """ Get the current block state
        
        This returns the current sensor state. 
        The block status may be:
        - Device.UNKNOWN: the block state is unknown
        - Device.BLK_EMPTY: the block is empty
        - Device.BLK_OCC: the block is occupied
        """
        return self._blk_state
    
    async def _get_reading(self):
        i2c_addr, conf = _adc_addr[self._adc]
        async with DCCBlkDet._i2c_lock:
            try:
                _i2c.writeto_mem(i2c_addr,_ADC_CONF_ADD,conf) # start read
                while True:
                    # let other stuff run
                    asyncio.sleep_ms(0)
                    res = _i2c.readfrom_mem(i2c_addr,_ADC_CONF_ADD, 2)
                    if (res[0] & 0x80) != 0:
                        break   # we have a result
                res = _i2c.readfrom_mem(i2c_addr, 0, 2) # read reg 0 (result register)
            except OSError:
                # i2c error - no track power most likely
                return None

        # this is a 12 bit signed (2's comp) value but left aligned.  L.S 4 bits always 0
        value = (res[0] << 4) + (res[1] >> 4)
        if (res[0] & 0x80) != 0:
            value = ((~value & 0x0fff) + 1) * -1
        return value
 




    async def _monitor(self):
        """ Coroutine to monitor current 

        This periodically reads the current sense analog input pin.

        The readings are processed to derrive two values.

        Firstly the base value representing 0 current is obtained.  This
        assumes that over a period of time that is sufficiently long compared
        with the DCC frequency and other periodic factors, the net current flow
        is zero. I.e there is no DC component in the current flow. Note that
        RailCom doesn't permit '0' stretching. Readings that might represent
        saturated op. amp. output are ignored as these may be asymetric.
        The remaining readings are filtered using a low pass Infinite Impulse
        Response (IIR) digital filter and the result is taken as being the zero
        offset. In theory the DCC signal measurement now uses a differential
        ADC so the offset should be 0 but in practice a small offset remains,
        possibly due to an offset error in the analogue amplifier.

        Secondly the value representing the current load is calculated.
        The input to this is the magnatude of the difference between the
        zero offset value and the reading. I.e. the absolute value without
        sign. The reading sampling runs asynchronously with respect to DCC
        and RailCom cutout timings. Atypically low values are assumed to be
        samples taken at DCC polarity change or during the RailCom cutout.
        These are filtered out by a non-linear LULU filter and
        the resulting values filtered using a low pass IIR filter.

        The filtered values are compared with two thresholds to determine
        whether the block is occupied. The thresholds apply hysterisis to
        avoid hunting.

        The coroutine task runs forever.

        """
        while True:
            await asyncio.sleep_ms(_TIMER_PERIOD)
            reading = await self._get_reading()
            if reading is None:
                # no power
                if self._blk_state != Device.BLK_NPOW:
                    self._blk_state = Device.BLK_NPOW
                    self.report_event(Device.BLK_NPOW, None)

            else:

                self._offset = self._offset * _Z_FILTER_RATIO + reading / _Z_FILTER_FACTOR
                
                # take the absolute difference between zero offset and the reading
                # and apply the LULU filter
                # Typically a LULU filter comprises two functions.  The L function
                # removes +ve going spikes and the U function removes -ve going
                # spikes. Here we only need the U function.

                self._readings.append(abs(reading - int(self._offset + 0.5)))
                if len(self._readings) > _LULU_SIZE:
                    self._readings.pop(0)
                        
                # LULU filter U funtion (width hard coded for buffer size 7)
                op_u = min(max(self._readings[0:3]),
                        max(self._readings[1:4]),
                        max(self._readings[2:5]),
                        max(self._readings[3:6]))

                # apply IIR low pass filter to this reading
                if self._readings[6] > self._av:
                    self._av = self._readings[6]
                else:
                    self._av = self._av * _FILTER_RATIO + op_u / _FILTER_FACTOR

                # check against thresholds
                if self._blk_state != Device.BLK_OCC and self._av > _U_THRESHOLD:
                    self._blk_state = Device.BLK_OCC
                    self.report_event(Device.BLK_OCC, None)
                elif self._blk_state != Device.BLK_EMPTY and self._av < _L_THRESHOLD:
                    self._blk_state = Device.BLK_EMPTY
                    self.report_event(Device.BLK_EMPTY, None)


if __name__ == '__main__':
    from led_pio import BlkLed
    async def lp():
        while True:
            Device.get_event_report(False)
            try:
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                break

    s = DCCBlkDet('t001',1, BlkLed(1))
    task = asyncio.run(lp())
