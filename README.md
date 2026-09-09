# Onkyo FlareConnect for Home Assistant

Control **FlareConnect** multiroom groups on Onkyo, Pioneer and Integra devices from Home
Assistant — group and ungroup speakers without the vendor app.

Unlike Chromecast groups, FlareConnect carries *any* source the master is playing, including
the **FM tuner** and analog inputs. That is something Cast and AirPlay cannot do.

## Why this exists

The official Onkyo Controller app is the only supported way to manage FlareConnect groups, and
it no longer works reliably on modern Android. Neither the group state nor the grouping command
appears in any published protocol documentation, so this integration is based on protocol
analysis of the app's own traffic.

## The protocol

Two undocumented eISCP commands on TCP port `60128` do all the work. Neither appears in the
official ISCP command list.

### `MDI` — read group state

`MDIQSTN` returns XML describing every zone:

```xml
<mdi>
  <deviceid>0009B0XXXXXX</deviceid>
  <netstandby>1</netstandby>
  <currentversion>200</currentversion>
  <zonelist>
    <zone id="1" groupid="88" ch="ST" role="src" roomname="Living room"
          groupname="" powerstate="1" iconid="0" color="0" delay="5000"/>
    ...
  </zonelist>
</mdi>
```

A group is nothing more than **the same `groupid` on every member**, with exactly one
`role="src"` (the master) and the rest `role="dst"`. When ungrouped, `groupid` is `0` and every
role is `none`. There is no member list in `MDI`: each device only reports its own zones.

### `MGS` — set group state

`MGS` is **write-only** — it does not answer `QSTN`, which is why scanning for commands never
reveals it. It is always sent to the **master**, which then drives the members:

```
group:    !1MGS<mgs zone="1"><groupid>88</groupid><maxdelay>5000</maxdelay>
               <devices><device id="0009B0XXXXXX" zoneid="1" /></devices></mgs>

ungroup:  !1MGS<mgs zone="1"><groupid>0</groupid></mgs>
```

`device id` is the member's MAC address without separators, exactly as reported in `<deviceid>`.
The `groupid` is yours to choose; the official app picks a fresh number each time. After the
change the app sends `MGV200` (the protocol version) to every device involved, which this
integration mirrors.

Group changes are **not pushed** over eISCP — not to the app, not to any other connection — so
state has to be polled.

## Why this integration does not poll

The built-in `onkyo` integration keeps a persistent eISCP connection open, and the receivers
push their state over it — volume, power, source. Opening a second connection knocks that one
off: the built-in integration then misses those pushes and has to re-query everything when it
reconnects, which shows up as `Disconnect detected` warnings and flickering media info. Measured
here: 95 disconnects in a single evening while polling every 15 seconds.

So this integration does **not** poll in the background. It reads group state on startup, right
after its own `join` / `unjoin`, and whenever you call `onkyo_flareconnect.refresh`. Group state
only changes when someone groups or ungroups anyway — the only case it can miss is grouping done
from the vendor app, and a `refresh` picks that up.

## Installation

### HACS

Add this repository as a custom repository of type *Integration*, install, and restart Home
Assistant.

### Manual

Copy `custom_components/onkyo_flareconnect` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

Settings → Devices & services → Add integration → **Onkyo FlareConnect**. Devices found through
eISCP discovery are prefilled; otherwise enter the IP addresses separated by commas.

## Entities

One sensor per device, `sensor.<room>_flareconnect_group`:

| | |
|---|---|
| State | `source`, `receiver` or `not grouped` |
| `group_id` | Current group number, `0` when ungrouped |
| `source` | Room name of the master |
| `members` | The other rooms in the group |
| `device_id` | MAC address, as used by the services |

## Services

### `onkyo_flareconnect.join`

| Field | Required | Description |
|---|---|---|
| `source` | yes | Master device — IP address or device id |
| `members` | yes | Devices that follow the master |
| `group_id` | no | Group number; picked automatically when omitted |
| `max_delay` | no | Audio delay in ms, default `5000` |

```yaml
action: onkyo_flareconnect.join
data:
  source: 192.168.1.10
  members:
    - 192.168.1.11
```

### `onkyo_flareconnect.unjoin`

```yaml
action: onkyo_flareconnect.unjoin
data:
  source: 192.168.1.10
```

## Tested on

Onkyo HT-R695 (master) and Onkyo NCP-302 (member), firmware `2151-0000-0000-0011-0000`.
Other FlareConnect and FireConnect devices use the same commands and should work; reports
welcome.
