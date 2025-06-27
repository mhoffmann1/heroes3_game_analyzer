

## How to run

python3 -m http.server 8000

## Current state

244.GM2 - Reads player resources correct, but uses know offsets instead of dynamic ones. No other save file will work


## To do

Link heroes to players: https://github.com/redxu/HoMM3_FA/blob/master/FA_struct.h#L12



Town regex:

🔥 Reliable Regex Match:
To match town names with the post-name marker:

css
Kopiuj
Edytuj
([\x01-\x0C].{1,12})\x04\x30\x2b\x05\x05\x58\x66\x19\x00
[\x01-\x0C]: length prefix (max town name length is 12).

.{1,12}: the town name itself.

Followed by the fixed marker.

## issues

Warning: AI Value not found for unit 'Leprechaun'



## Ideas

Percentage of map discovered
Number of Dragon Utopia Visited
Number of towns
DD, TP, Fly - mark if available to hero