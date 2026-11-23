# Home Assistant + Galactic display

## Goal and design

- **Apple Home stays in charge.** The Apple TV 4K remains the home hub and Thread border
  router. If the Mac mini is off, every device and Apple Home automation keeps working.
- **Home Assistant (HA) is an optional layer** on the Mac mini: it watches the home and talks
  to the display. When it's off, only the HA-driven display features pause.
- **HA and the display talk through ntfy**, which the board already uses. Messages travel via
  the internet relay, so no firewall changes are needed between the IoT network and the main
  network.

```
 Eve devices ──Thread──► Apple TV 4K (border router, main network)
                               │  Matter (shared, multi-admin)
                               ▼
                 Home Assistant VM on the Mac mini (main network, Ethernet)
                               │  ntfy integration
                               ▼
                    ntfy.sh ◄──────► Galactic Unicorn (IoT network)
```

| Your setup | Where it lives |
|---|---|
| UniFi Cloud Gateway Fiber | router, VLANs, firewall |
| Apple TV 4K (2021), Wi-Fi | main network, Thread border router |
| Mac mini (Intel), always on | main network over **Ethernet** → runs the HA virtual machine |
| Galactic Unicorn (Pico W) | IoT network |
| Eve Energy, Eve Weather, Eve Motion | Thread (through the Apple TV) |

Why HA goes on the **main** network: Matter and Thread rely on IPv6 and multicast discovery,
which don't cross VLANs reliably. HA's own docs recommend keeping HA on the same network as
the Thread border router (the Apple TV). Use **Ethernet** for the VM's bridge: virtual
machines bridged over Wi-Fi often lose the multicast traffic Matter needs.

---

## Phase 1: Install Home Assistant on the Mac mini (about 45 minutes)

### 1.1 Prepare the Mac

1. **Check macOS:** Apple menu → **About This Mac**. Note the version (likely macOS 15
   Sequoia or earlier on an Intel Mac mini).
2. **Connect Ethernet** to the main network. Wi-Fi can stay on.
3. **Keep it awake:** System Settings → **Energy** (or Energy Saver): turn on *Prevent
   automatic sleeping when the display is off* and *Start up automatically after a power
   failure*.

### 1.2 Install VirtualBox

1. Download **VirtualBox for macOS / Intel hosts** from https://www.virtualbox.org/wiki/Downloads
   and install it.
2. If macOS blocks a system extension from Oracle: System Settings → **Privacy & Security** →
   *Allow*, then restart the Mac.

### 1.3 Download Home Assistant OS

1. Open https://www.home-assistant.io/installation/macos
2. Under *Download the appropriate image*, download **VirtualBox (Intel chip) (.vdi)**.
3. Unzip it. Move the `.vdi` file somewhere permanent (e.g. a `Home Assistant` folder in your
   home folder). The virtual machine runs from this file.

### 1.4 Create the virtual machine

In VirtualBox:

1. **New**
   - Name: `Home Assistant`
   - ISO Image: leave blank
   - OS: **Linux**, Distribution/Version: **Oracle Linux (64-bit)**
2. Hardware:
   - Base Memory: **4096 MB** if the Mac has 16 GB or more, otherwise 2048 MB
   - CPUs: **2**
   - **Use EFI: on** (required)
3. Hard disk: **Do not add a virtual hard disk** → Finish (confirm *Continue* if asked).
4. Select the VM → **Settings** → **Storage** → next to *Controller: SATA*, click the
   **add hard disk** icon → **Add** → choose your `.vdi` → **Choose**.
5. **Settings** → **Network** → Adapter 1: *Attached to* **Bridged Adapter**, *Name*: your
   **Ethernet** adapter (usually `en0: Ethernet`). → **OK**.

### 1.5 First start

1. Select the VM → **Start** (or the arrow next to it → **Headless Start** to run without a
   window).
2. Wait. The first boot downloads the latest Home Assistant and can take **10–20 minutes**.
3. On the Mac, open **http://homeassistant.local:8123**. If that doesn't load, look in the
   UniFi app under **Clients** for a device named `homeassistant` and open
   `http://<its IP>:8123`.
4. Create your Home Assistant account, set your home location, and finish the setup wizard.
   HA will offer devices it discovers. Skip anything you don't recognise for now.

### 1.6 Make it permanent

1. **Fixed address:** UniFi → **Clients** → `homeassistant` → **Settings** → enable
   **Fixed IP Address**. This keeps the address stable.
2. **Start with the Mac:** VirtualBox doesn't start VMs on boot by itself. The simplest
   approach is to start it when you log in:
   1. Open **Script Editor** and paste:
      ```applescript
      do shell script "/usr/local/bin/VBoxManage startvm 'Home Assistant' --type headless"
      ```
   2. **File → Export**, File Format **Application**, save it as `Start Home Assistant` in
      Applications.
   3. System Settings → **General → Login Items** → **+** → add `Start Home Assistant`.
   4. For this to run after a power cut, the Mac must log in automatically (System Settings →
      **Users & Groups → Automatically log in as**). macOS doesn't offer that while FileVault
      is on. If you use FileVault, start the VM by hand after a power cut instead.
3. **Shut down cleanly:** before restarting the Mac, stop HA from **Settings → System →
   ⋮ (top right) → Shut down system**, or let macOS close VirtualBox (it saves the VM state).

**Done when:** `http://homeassistant.local:8123` loads after you restart the Mac.

---

## Phase 2: Let Home Assistant see your Eve devices

HA can only share devices that are in **Matter** mode. A device paired with Apple Home as a
classic **HomeKit** accessory can belong to only one controller, and taking it away from
Apple Home goes against the goal above.

### 2.1 Check which mode each Eve device is in

In the **Home** app → long-press the device → **Accessory Settings** (scroll down):

- **Matter**: the settings show Matter information and a **Turn On Pairing Mode** option.
  → Can be shared with HA (2.3).
- **HomeKit only**: no Matter option. Eve has released Matter firmware for its Thread
  devices. The **Eve** app shows whether yours can switch. Switching means removing the
  device from Apple Home and adding it again as a Matter device (rooms and automations
  that use it need re-doing). Decide per device. You can also leave them as they are; HA
  just won't see them.

### 2.2 Prepare Home Assistant

1. HA: **Settings → System → Network** → IPv6: **Automatic** → Save.
2. HA: **Settings → Devices & services → Add integration → Matter** → Submit. This installs
   the Matter server.
3. **Thread** appears by itself under Devices & services once HA sees the Apple TV. It
   should list an Apple border router.
4. iPhone: install the **Home Assistant** app from the App Store and sign in to your HA
   (be on the main Wi-Fi network at home).

### 2.3 Share each Matter device

1. **Home** app → the device → Accessory Settings → **Turn On Pairing Mode** → copy the
   setup code.
2. **Home Assistant** app → **Settings → Connectivity → Matter → Add device** →
   **Yes, it's already in use** → **Apple Home** → follow the steps and enter the code.
3. The device now appears in both apps. Apple Home stays the primary controller.

**Known limit:** HA can't update the firmware of Thread devices behind an Apple border router.
Keep updating Eve devices through the Home or Eve app as before.

---

## Phase 3: Home Assistant ↔ display

### 3.1 HA sends to the display

1. HA: **Settings → Devices & services → Add integration → ntfy**.
   - Service URL: `https://ntfy.sh`
   - **Add topic** → **Enter topic** → your display's topic (the `NTFY_TOPIC` in the board's
     `secrets.py`) → Display name `Galactic display`.
2. Test: **Developer tools → Actions** → choose the `notify.send_message` action for the
   *Galactic display* entity, message `Hello from Home Assistant` → **Perform action**.
3. Example automation (**Settings → Automations → Create → Create new automation** →
   ⋮ **Edit in YAML**):

   ```yaml
   alias: Motion on the display
   triggers:
     - trigger: state
       entity_id: binary_sensor.eve_motion_occupancy   # pick yours from the list
       to: "on"
   actions:
     - action: notify.send_message
       target:
         entity_id: notify.galactic_display              # pick yours from the list
       data:
         message: "Motion in the office"
   ```

The display's priorities and colour tags (see the main README) apply here too.

### 3.2 Display sends to HA (planned)

The display's buttons can trigger HA scenes by publishing to a **second** ntfy topic that HA
subscribes to (the ntfy integration exposes received messages as an event entity). This needs
a small addition on the board, done once Phase 3.1 works.

---

## Troubleshooting

| Problem | Check |
|---|---|
| `homeassistant.local` doesn't load | Use the IP from UniFi Clients. First boot can take 20 minutes. |
| VM has no network / no IP | VM Settings → Network: Bridged to **Ethernet**, and the Ethernet cable is connected to the main network. |
| Matter device won't add | Phone, Apple TV and HA all on the main network; HA IPv6 = Automatic; try again close to the Apple TV. In UniFi, avoid Wi-Fi settings that filter or "optimise" multicast on the main network (e.g. *Multicast and Broadcast Control*). |
| Thread integration shows no Apple border router | Apple TV awake and on the main Wi-Fi; HA IPv6 = Automatic; restart HA. |
| Display doesn't show HA messages | Topic in HA exactly matches the board's `NTFY_TOPIC`; test with a browser at https://ntfy.sh/app. |
