# Notes

## TODO
[x] Log only INFO and up
[x] Add guid to all payloads on make and receive
[x] Check mutliprocess event loop
[x] add battery state to wake up and sleep
[x] dont print forwarding
[x] Mega sync must not circle
[x] Mega sync duplicates
[x] Mega sync send from gateway
[x] Mega sync request gateway from node hopcnt=0
[x] Add last maps
[x] Duplicate removal works and is not behaving bad
[] Hopcnt can do all maps
[] Megasync can adjust time to is needed
[] Minisync can adjust time to is needed
[] Implement unlinear clock and make it behave using minisync and megasync
[] Add deduplication compression, when buffers are filling up, due to congestion


## Stuff the protocol should get, if time was for it?
- Check if we dont have time in TDMA slot to send the current package, do we have smaller packet we could send in buffer?
- If own hopcnt changes, tx current hopcnt packet

## Stuff the simulator cannot, that should have been done?