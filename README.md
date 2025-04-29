# rp2da2

 Model Railway Distributed Automation for RP2 (and other MicropPython MCUs).

---

## Software Modules

**device** - This provides the Device class, a base class for hardware device drivers and similar objects.

**oled0_91** - Module for 0.91 inch OLED on i2c

**screen** - This is the screen application module. It specifies the Screen class.

**dcc_cmd_pio** - This module contains the class and functions for low level DCC Command Serialisation for use with RailCom detection.

**dcc_cmd_util** - This module contains classes for DCC command objects.

**dcc_command** - This module provides high level APIs. It and associated modules contain the functions and classes for DCC command station.

**dcc_rc_ch1** - This module contains the functions and classes for DCC RailCom block detection on Channel 1.

**dcc_rc_ch2** - This module contains the functions and classes for DCC RailCom DCC command mobile responses on Channel 2.

**dcc_rc_pio**  - This module contains the functions and classes for low level RailCom datagram reading. It's applicable for block occupancy detection on Channel 1 and central dcc command decoder responses on Channel 2.

---

## DCC API

### Module dcc_command

---
class **DCCCommand** *(DCC_pn, sleep_pn, gen_sm_num, enable_pn)*

Parameters

- *DCC_pn* Pin number allocated for DCC output.

- *sleep_pn* Pin number allocated to the booster for powering the track

- *gen_sm_num* PIO state machine number to be used for DCC Generation

- *enable_pn* Pin number to enable the DRV8874.

---

method **power** *(p=None)*

DCC Power On/Off

Start and stop command packet transmission scheduling.

Parameters

- *p* 1 for power on, 0 for power off, None for get power status

Returns

- power status as held by the DCC generator.

---

method **read_cv** *(address, cv_num)*

This initiates reading a CV using Programming on Main in conjunction with RailCom.
The command is validated and the read request scheduled for action. The addressed decoder must be active and the command will be rejected by the command generator class this is not true.

Parameters

- *address*

- *cv_num* cv number as entered - users count from 1, DCC counts from 0!

---

method **write_cv** *(address, cv_num, new_val)*

This initiates writing a CV using Programming on Main in conjunction with RailCom.

The command is validated and the write request scheduled for action. The addressed
decoder must be active and the command will be rejected by the command generator class
this is not true.

Parameters

- *address*

- *cv_num* cv number as entered - users count from 1, DCC counts from 0!

- *new_val* the new value for the CV

method **set_fg1** *(address, f_num, state)*

Set Function Group 1

This sets or clears a function in group 1. The forward light is usually function number 0.

See NMRA S-9.2.1 Section 2.3.4

Parameters

- *address* the address of the decoder - may be short or long

- *f_num* function number to set or clear

- *state* 1 for set, 0 for clear

Returns

- True if validation is passed and the packet is scheduled for transmission. False if validation fails.

---

**set_speed** *(address, dir, speed=0)*

Set Speed (including direction)

The packet generated will be for a 128 step speed setting and decoders must be configured for 28/128 speed steps.

See NMRA S-9.2.1 Section 2.3.2.1

Parameters

- *address* the address of the decoder - may be short or long

- *dir* the direction - forward or reverse

- *speed* the speed to be set - range 0 to 127 - default 0

Returns

- True if validation is passed and the packet is scheduled for transmission. False if validation fails.

---

Available constants are:

```py
# Forward direction
FWD = const(1)

# Reverse Direction
REV = const(-1)

# Power Off
OFF = const(0)

# Power On
ON = const(1)
```

---

### DCC Diagnostics

---
Module dcc_command

function **print_stats** *(reset = True)*

This prints diagnostic information on DCC commands
and RailCom. By default the diagnostics are cleared after being printed.
