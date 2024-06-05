import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi
import smbus
import time
import struct
import logging
import RPi.GPIO as GPIO

# Set up your x728 according to instructions: https://wiki.geekworm.com/X728-script
# Based on scripts at: https://github.com/geekworm-com/x728-script/tree/main
# UI elements based on pysugar2: https://github.com/tisboyo/pwnagotchi-pisugar2-plugin/blob/master/pisugar2.py
class x728(plugins.Plugin):
    __author__ = 'uasmatrix@aim.com'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'Uses GPIO pins from Geekworm x728 to get battery levels and safely shut down if needed'

    CHARGE_SYMBOL = "\u26A1"
    BATTERY_SYMBOLS = {13:"\u2581",
                       25:"\u2582",
                       38:"\u2583",
                       50:"\u2584",
                       63:"\u2585",
                       75:"\u2586",
                       88:"\u2587",
                       100:"\u2588"}

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.i2c_addr = None
        self.gpio_pin = None
        self.shutdown_percent = None
        self.shutdown_threshold_time = 0
        self.power_pin = None
        self.bus = None
        logging.debug("x728 plugin created")

    def on_loaded(self):
        if 'gpio_pin' not in self.options or not self.options['gpio_pin'] or int(self.options['gpio_pin']) <= 0:
            logging.error("[x728:on_loaded]: Missing or invalid 'gpio_pin' config option. Will not run.")
            return
        if 'i2c_addr' not in self.options or not self.options['i2c_addr'] or int(self.options['i2c_addr']) <= 0:
            logging.error("[x728:on_loaded]: Missing or invalid 'i2c_addr' config option. Will not run.")
            return
        if 'shutdown_percent' not in self.options or not self.options['shutdown_percent'] or int(self.options['shutdown_percent']) < 0:
            logging.error("[x728:on_loaded]: Missing or invalid 'shutdown_percent' config option. Will not run.")
            return
        if 'power_pin' not in self.options or not self.options['power_pin'] or int(self.options['power_pin']) <= 0:
            logging.error("[x728:on_loaded]: Missing or invalid 'power_pin' config option. Will not run.")
            return
        
        self.gpio_pin = int(self.options['gpio_pin'])
        self.i2c_addr = int(self.options['i2c_addr'])
        self.shutdown_percent = int(self.options['shutdown_percent'])
        self.power_pin = int(self.options['power_pin'])
        self.bus = smbus.SMBus(1) # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)
        GPIO.setup(self.power_pin, GPIO.IN)
        GPIO.setwarnings(False)

        self.ready = True
        logging.info("[x728]: Plugin loaded")

    def read_voltage(self):
        read = self.bus.read_word_data(self.i2c_addr, 2)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        voltage = swapped * 1.25 /1000/16
        return voltage

    def read_capacity(self):
        read = self.bus.read_word_data(self.i2c_addr, 4)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        capacity = min(swapped/256, 100)
        return int(capacity)

    def get_battery_symbol(self, capacity):
        for k,v in self.BATTERY_SYMBOLS.items():
            if capacity <= k:
                return v

    def is_charging(self):
        return GPIO.input(self.power_pin) == GPIO.LOW

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element(
                "x728bat",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value=self.BATTERY_SYMBOLS[100],
                    position=(ui.width() / 2 + 21, 2),
                    label_font=fonts.Bold,
                    text_font=fonts.Small,
                ),
            )
            ui.add_element(
                "x728batpct",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value="-%",
                    position=(ui.width() / 2 + 26, 0),
                    label_font=fonts.Bold,
                    text_font=fonts.Medium,
                ),
            )
            ui.add_element(
                "x728chg",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value="",
                    position=(ui.width() / 2 + 13, 0),
                    label_font=fonts.Small,
                    text_font=fonts.Medium,
                ),
            )

    def on_ui_update(self, ui):
        if self.ready:
            capacity = self.read_capacity()
            is_charging = self.is_charging()

            if is_charging:
                ui.set("x728chg", self.CHARGE_SYMBOL)
            else:
                ui.set("x728chg", "")

            ui.set("x728bat", self.get_battery_symbol(capacity))
            ui.set("x728batpct", str(capacity) + "%")

            if capacity <= self.shutdown_percent and not is_charging:
                if self.shutdown_threshold_time == 0:
                    self.shutdown_threshold_time = time.time()
                elif time.time() - self.shutdown_threshold_time >= 120:
                    # When the device first turns on, the capacity seems to get calculated over time
                    # So even if fully charged, it will start at low capacity and climb over time until it reaches the real value
                    # To avoid thinking it's actually at a low charge, we give it a 2 minute window where if it remains
                    # <= the shutdown capacity for 2 minutes, we will consider it valid and shut down
                    logging.info(
                        f"[x728] Empty battery (<= {self.shutdown_percent}): shutting down"
                    )
                    ui.update(force=True, new_data={"status": "Battery exhausted, bye ..."})
                    time.sleep(3)
                    pwnagotchi.shutdown()
                    #time.sleep(10)
                    #GPIO.output(self.gpio_pin, GPIO.HIGH)
                    #time.sleep(3)
                    #GPIO.output(self.gpio_pin, GPIO.LOW)
            elif self.shutdown_threshold_time > 0:
                self.shutdown_threshold_time = 0

    def on_unload(self, ui):
        self.ready = False
        with ui._lock:
            ui.remove_element("x728bat")
            ui.remove_element("x728batpct")
            ui.remove_element("x728chg")
        logging.info("[x728]: Plugin unloaded")
