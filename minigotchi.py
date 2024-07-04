import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK
import serial
import json
import logging


# install pyserial
# enable serial pins in raspi-config
# add 'enable_uart=1' to boot config
class Minigotchi(plugins.Plugin):
    __author__ = 'uasmatrix@aim.com'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'Uses GPIO pins or USB serial to communicate between your Pwnagotchi and Minigotchi to sync channels'

    def __init__(self):
        self.ready = False
        self.ser = None
        self.options = dict()
        self.status = "-"
        self.syncState = ""
        self.name = "Minigotchi"
        logging.debug("Minigotchi plugin created")

    def on_loaded(self):
        if 'baud_rate' not in self.options or not self.options['baud_rate']:
            logging.error("[Minigotchi:on_loaded]: Missing 'baud_rate' config option. Will not run.")
            return
        if 'serial_port' not in self.options or not self.options['serial_port']:
            logging.error("[Minigotchi:on_loaded]: Missing 'serial_port' config option. Will not run.")
            return
        if 'read_timeout' not in self.options or not self.options['read_timeout']:
            logging.error("[Minigotchi:on_loaded]: Missing 'read_timeout' config option. Will not run.")
            return
        if 'write_timeout' not in self.options or not self.options['write_timeout']:
            logging.error("[Minigotchi:on_loaded]: Missing 'write_timeout' config option. Will not run.")
            return
        
        try:
            self.ser = serial.Serial(port=self.options['serial_port'], baudrate=int(self.options['baud_rate']), timeout=float(self.options['read_timeout']), write_timeout=float(self.options['write_timeout']))
            self.ser.flush()
        except Exception as e:
            logging.error("[Minigotchi:on_loaded]: Error trying to load serial, will not run -> %s" % e)
            return

        self.ready = True
        logging.info("[Minigotchi]: Plugin loaded")

        # Start off by requesting the lil guy's name
        try:
            msg = "nme:::1\n".encode()
            self.ser.write(msg)
        except Exception as e:
            logging.error("[Minigotchi:on_loaded]: Error writing name request to serial -> %s" % e)

    def on_channel_hop(self, agent, channel):
        if self.ready:
            try:
                msg = "chn:::{chn}\n".format(chn=channel).encode()
                self.ser.write(msg)
            except Exception as e:
                logging.error("[Minigotchi:on_channel_hop]: Error writing channel to serial -> %s" % e)

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('minigotchiname', Text(color=BLACK, 
                                                  value='Minigotchi',
                                                  position=(1, int(ui.height() * 0.75) - 5),
                                                font=fonts.Small,))
            ui.add_element('minigotchistatus', Text(color=BLACK, 
                                                    value='-',
                                                    position=(1, int(ui.height() * 0.75) + 4),
                                                    font=fonts.Small,))
    def on_ui_update(self, ui):
        try:
            while self.ready and self.ser and self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8').rstrip()
                if line and line != "":
                    parts = line.split(':::', 2)
                    if parts and len(parts) == 2 and len(parts[0]) == 3:
                        action = parts[0]
                        jsonData = None
                        try:
                            jsonData = json.loads(parts[1])
                        except Exception as e:
                            logging.error("[Minigotchi.on_ui_update]: Error parsing JSON %s -> %s", parts[1], e)
                            continue
                        data = jsonData.get('data', None)
                        code = int(jsonData['status'])
                        if action == "nme":
                            self.name = data
                        elif action == "chn":
                            if code == 200:
                                self.syncState = "(S)"
                                # TODO: data in this case is the synced channel, can use somewhere if desired
                            elif code == 201:
                                self.syncState = ""
                        elif action == "adv":
                            self.status = "Advertising myself"
                        elif action == "pwn":
                            if code == 200:
                                self.status = "Looking for friends"
                            elif code == 201:
                                self.status = "Found a friend! ({fnd})".format(fnd=data)
                            elif data == 202:
                                self.status = "No friends found :("
                            elif data == 250:
                                self.status = "Error while looking for friends"
                        elif action == "atk":
                            if  code == 200:
                                self.status = "Scanning..."
                            elif code == 202:
                                self.status = "No APs found"
                            elif code == 201 or code == 203:
                                deauthData = None
                                try:
                                    deauthData = json.loads(data)
                                except Exception as e:
                                    logging.error("[Minigotchi.on_ui_update]: Error parsing deauth JSON %s -> %s", data, e)
                                if deauthData:
                                    ssid = deauthData["ssid"]
                                    chn = deauthData["channel"]
                                    if code == 201:
                                        self.status = "Selected {ssid} (ch: {chn})".format(ssid=ssid, chn=chn)
                                    else:
                                        self.status = "Deauthing {ssid} (ch: {chn})".format(ssid=ssid, chn=chn)
                            elif code == 210:
                                self.status = "Skipping deauth (AP whitelisted)"
                            elif code == 211:
                                self.status = "Skipping deauth (AP not encrypted)"
                            elif code == 250:
                                self.status = "Error while scanning"
                        else:
                            self.status = "Unknown?"
                    else:
                        logging.debug("[Minigotchi.on_ui_update]: Disregarding unknown data -> %s" % line)
        except Exception as e:
            logging.error("[Minigotchi.on_ui_update]: Error reading from serial -> %s" % e)

        with ui._lock:
            ui.set('minigotchiname', "{name} {sync}".format(name=self.name, sync=self.syncState))
            ui.set('minigotchistatus', self.status)

    def on_unload(self, ui):
        self.ready = False
        with ui._lock:
            ui.remove_element('minigotchiname')
            ui.remove_element('minigotchistatus')

        if self.ser:
            try:
                self.ser.close()
            except Exception as e:
                logging.error("[Minigotchi:on_unload]: Error closing serial -> %s" % e)
            finally:
                self.ser = None

        logging.info("[Minigotchi]: Plugin unloaded")