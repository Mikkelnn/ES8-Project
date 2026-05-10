# Notes

## TODO
[x] Log only INFO and up
[x] Add guid to all payloads on make and receive
[x] Check mutliprocess event loop
[] _flush_tx_buffers DLL potential issue
[] add battery state to wake up and sleep
[] dont print forwarding
[] Mega sync must not circle
[] Mega sync duplicates

## Stuff the protocol should get, if time was for it?
- Check if we dont have time in TDMA slot to send the current package, do we have smaller packet we could send in buffer?
- If own hopcnt changes, tx current hopcnt packet

## Stuff the simulator cannot, that should have been done?