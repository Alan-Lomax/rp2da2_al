"""Test harness for DCC Local Railcom channel 1 module.


This script is designed to run on a Raspberry Pi Pico or Arduino Nano Connect acting as a dual local detector.
It initializes the necessary pins and starts the RailCom channel 1 detectors.
It also includes a thread to display event reports and prints statistics about detection.

It uses the machine module for hardware interaction and the device module for event reporting.

"""



import _thread, time, sys

from micropython import alloc_emergency_exception_buf

from machine import Pin, ADC

from device import Device
from dcc_rc_ch1 import RComBlkDet
from dcc_rc_pio import RailComRead
from led_pio import BlkLed
from screen import Screen


alloc_emergency_exception_buf(100)

if __name__ == '__main__':

    ERR_CODE_DECODE = {
        RailComRead.ERR_WH:'W_HIGH',
        RailComRead.ERR_WL:'W_LOW',
        RailComRead.ERR_OE:'OVERRUN',
        RailComRead.ERR_CB:'CB_IN_DG',
        RailComRead.ERR_FE:'DG_INCOMP',
        RailComRead.ERR_ID:'UNRECOG_DG',
        RailComRead.ERR_PL:'PAYLD_ERR',
        RailComRead.ERR_RESP:'SYNC_ERR'}


    build = sys.implementation._build # get build details
    
    if build.find("PICO2") > -1:
        # Detector pin allocations - Raspberry Pi Pico format
        c1a_rx_pin = 14
        c1b_rx_pin = 16
        c1c_rx_pin = 18
        c1d_rx_pin = 20
    elif build.find("PICO") > -1:
        # Detector pin allocations - Raspberry Pi Pico format
        c1a_rx_pin = 14
        c1b_rx_pin = 16
    elif build.find("NANO") > -1:
        # Detector pin allocations - Arduino Nano  format
        c1a_rx_pin = 0
        c1b_rx_pin = 15

        # second Dual reader - these pins are used for DRV8874
        # on command station

        c1c_rx_pin = 18
        c1d_rx_pin = 20
    else:
        print (build, "invalid")


    time_stamp = time.ticks_ms()

    block_list = (RComBlkDet('t001', 0, c1a_rx_pin, BlkLed(1)),
                RComBlkDet('t002', 2, c1b_rx_pin, BlkLed(2)),
                RComBlkDet('t003', 4, c1c_rx_pin, BlkLed(3)),
                RComBlkDet('t004', 6, c1d_rx_pin, BlkLed(4)))
    
    def main1():
        # bypass screen module to avoid pulling in MQTT & WiFi
        s = Screen()

        while True:
            report = Device.get_event_report(False)
            
            if report is not None:
                s.show_event(report)


            

    def print_stats(reset = True):
        global time_stamp
        elapsed_time = time.ticks_diff(time.ticks_ms(), time_stamp)  
        for block in (block_list):
            counts = block.get_error_counts()
            cb_count = block.get_cb_count()
            print(f'** Channel 1 block {block.get_name()} **')
            print(f"Call back rate: {(cb_count) * 1000 / elapsed_time:.2f} per sec")
            for key, value in counts.items():
                print(f'{ERR_CODE_DECODE[key]}\t{value}')
            
            if cb_count > 0:
                print(f"err. rate: {(sum(counts.values())/cb_count):.0%}")
            if reset:
                block.reset_stats()
        time_stamp = time.ticks_ms()

    _thread.start_new_thread(main1,())





