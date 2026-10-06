<img src="custom_components/btproxy_health/brand/icon.png" alt="" width="96" align="right">

# Bluetooth Proxy Health

A Home Assistant integration that tells you when a Bluetooth proxy **stops proxying**: online, pingable and reporting normal sensors, while passing no Bluetooth traffic at all.

## Why

An ESPHome Bluetooth proxy can fail in ways that nothing in Home Assistant reports:

| Failure | What you see | Usual fix |
|---|---|---|
| **Frozen** | Board unreachable, no reboot | Power cycle |
| **Connected but deaf** | Online, pingable, heap and loop time normal, but zero advertisements, sometimes for hours | Restart the board |
| **Hears, cannot connect** | Devices heard at good signal, but every connection times out | Restart the board |

Heap, loop-time and reset-reason sensors on the board catch crashes, not these. Home Assistant's scanner watchdog notices a quiet remote proxy only at debug log level, and raises no repair or notification. Your curtains, mugs and sensors just stop updating.

This integration reads what Home Assistant's Bluetooth integration already knows about each scanner, such as when it last *received* an advertisement from it, and turns that into sensors you can alert on. It checks end to end, needs no firmware change, and never restarts anything itself.

## What you get

Five diagnostic sensors on **each proxy's existing device**. It creates no new devices.

| Sensor | Meaning | Healthy |
|---|---|---|
| **Last advertisement** | Seconds since the proxy last delivered any advertisement | Roughly 0–40 s in a busy house |
| Connection failures (1 h) | Failed connection attempts through this proxy in the last hour | Varies; 20–40/h is normal near sleepy devices. Baseline before alerting |
| Connections (1 h) | Successful connections in the last hour | Depends on what uses the proxy; zero is not a fault |
| Connections in progress | Connection attempts in flight right now | 0–1 |
| Devices heard | Devices the proxy currently hears | Steady for a given location |

- Values update every 60 seconds.
- The hourly counts carry `window_complete: false` for the first hour after Home Assistant starts.
- **A disconnected proxy's sensors go `unavailable` instead of disappearing.** The list of proxies comes from the Bluetooth integration's per-scanner config entries, which survive a disconnect. Proxies added later get sensors automatically, and a proxy you replace or retire (its Bluetooth entry deleted) loses them.
- Every remote scanner is covered (ESPHome, Shelly and other proxies). Local USB/UART adapters are not proxies and are skipped.
- ESPHome proxies keep their existing entity-ID prefix, which is taken from the restart button. For example, a proxy with `button.esp32_bluetooth_proxy_a1b2c3_restart` gets `sensor.esp32_bluetooth_proxy_a1b2c3_last_advertisement`. Other proxies get Home Assistant's default IDs.

## Installation

**HACS (custom repository):** HACS → ⋮ → *Custom repositories* → add `https://github.com/meeowgler/btproxy-health-homeassistant` as an *Integration*. Install **Bluetooth Proxy Health**, then restart Home Assistant.

**Manual:** copy `custom_components/btproxy_health/` into your `config/custom_components/` and restart Home Assistant.

Then go to *Settings → Devices & services → Add integration → Bluetooth Proxy Health*. There is a single confirm step and nothing to configure.

Requires Home Assistant **2026.9** or later.

## Alerting

The integration only provides sensors; how you alert is up to you. One template sensor covers the whole fleet. Create it under *Settings → Devices & services → Helpers → Create helper → Template → Template sensor*:

```jinja
{%- set limit_min = 15 -%}
{%- set sensors = integration_entities('btproxy_health') | select('search', '_last_advertisement$') | list -%}
{%- set ns = namespace(bad=[]) -%}
{%- for s in sensors -%}
  {%- set dev = device_id(s) -%}
  {%- set name = (device_attr(dev, 'name_by_user') or device_attr(dev, 'name')) if dev else none -%}
  {%- set name = name or state_attr(s, 'friendly_name') or s -%}
  {%- set st = states[s] -%}
  {%- if st.state in ['unavailable', 'unknown'] -%}
    {%- if now() - st.last_changed > timedelta(minutes=limit_min) -%}
      {%- set ns.bad = ns.bad + [name ~ ' offline'] -%}
    {%- endif -%}
  {%- elif st.state | float(0) > limit_min * 60 -%}
    {%- set ns.bad = ns.bad + [name ~ ' deaf ' ~ ((st.state | float(0)) / 60) | round(0) | int ~ ' min'] -%}
  {%- endif -%}
{%- endfor -%}
{%- if sensors | count == 0 -%}
Proxy health integration not loaded
{%- elif ns.bad | count == 0 -%}
OK
{%- else -%}
{{ ns.bad | join(', ') }}
{%- endif -%}
```

It reads `OK`, or names each problem proxy, e.g. "Kitchen proxy deaf 17 min, Garage proxy offline". The 15-minute grace means a proxy reboot or a Home Assistant restart won't trigger it. It reports *not loaded* rather than `OK` if the integration's sensors are missing, so a broken install can't pass for healthy. Trigger a notification on any state other than `OK`, or put it on a dashboard.

## Caveats

- **Two sensors read library internals.** *Last advertisement*, *Connections in progress* and *Devices heard* use only public Bluetooth integration calls. The two hourly connection counts read `habluetooth` counters (`_connect_failed_total`, `_connect_completed_total`) that have no public accessor. If a future release renames them, those two sensors go `unavailable` and one error is logged. The liveness sensor keeps working.
- **Alerts only.** Restarting a proxy automatically is deliberately left out. A proxy that keeps going deaf usually has a cause (Wi-Fi, power, firmware) worth finding.
- After updating this integration, restart Home Assistant. Reloading the config entry does not load new code.

## How it works

Every remote scanner registers a config entry in the `bluetooth` integration whose data includes the source (the proxy's Bluetooth MAC) and the device it belongs to. This integration lists those entries, looks each source up with `bluetooth.async_scanner_by_source()`, and reads `time_since_last_detection()` and the connection counters every 60 seconds. Entities link to the proxy's own device through `Entity.device_entry`. Since Home Assistant 2026.9, `DeviceInfo(connections=...)` would create a duplicate device instead.

## License

MIT
