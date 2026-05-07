""" Local Detector Board Block Occupancy Check

May be run as part of commissioning a newly constructed board as a check on
connection, soldering and functional integrity.

Requires device.py, blk_mon.py and led_pio.py

"""

import asyncio

from device import Device
from blk_mon import DCCBlkDet

if __name__ == '__main__':
    from led_pio import BlkLed
    async def lp():
        while True:
            Device.get_event_report(False)
            try:
                await asyncio.sleep_ms(1)
            except KeyboardInterrupt:
                break

    s = [DCCBlkDet('t1',0, BlkLed(1)),
         DCCBlkDet('t2',1, BlkLed(2)),
         DCCBlkDet('t3',2, BlkLed(3)),
         DCCBlkDet('t4',3, BlkLed(4))]
         
    task = asyncio.run(lp())