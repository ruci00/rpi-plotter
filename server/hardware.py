from mathextra import *
import RPi.GPIO as GPIO
from time import sleep


class NotCalibratedError(Exception):
    def __str__(self):
        return "Plotter is not calibrated!"


class BadCommandError(Exception):
    def __str__(self):
        return "Bad command!"


class ShiftRegister:
    t = 0

    def __init__(self, data, clock, latch, count=1):
        self.data = data
        self.clock = clock
        self.latch = latch
        self.count = count
        GPIO.setup(data, GPIO.OUT)
        GPIO.setup(clock, GPIO.OUT)
        GPIO.setup(latch, GPIO.OUT)
        GPIO.output(latch, False)
        GPIO.output(clock, False)
        self.pin = list(range(count*8))
        for p in self.pin:
            self.pin[p] = False

    def cmd(self, cmd):
        for state in str(cmd):
            GPIO.output(self.data, int(state))
            GPIO.output(self.clock, True)
            sleep(self.t)
            GPIO.output(self.clock, False)
            sleep(self.t)
        GPIO.output(self.latch, True)
        sleep(self.t)
        GPIO.output(self.latch, False)

    def state(self, pin):
        return self.pin[pin]

    def update(self):
        output = ''
        for ps in self.pin:  # ps pin State
            output = str(int(ps)) + output
        self.cmd(output)
        return True

    def output(self, *args):
        for out in args:  # WTF is this? Give the example of this, I don't undrstnd
            if out[0] >= self.count*8:
                # todo state is not 0 or 1
                return False  # pin out of range
            self.pin[out[0]] = out[1]
        self.update()
        return True
    
    def output(self, *states):
        if type(states[0]) is not list:
            states = ([[states[0], states[1]]])
        for out in states:
            if out[0] >= self.count*8:
               return False #pin out of range #todo state is not 0 or 1
            self.pin[out[0]] = out[1]
        self.update()
        return True


class ATX:
    def __init__(self, highCurrent, load, sr):
        self.highCurrent = highCurrent
        self.load = load
        self.sr = sr
        sr.output([highCurrent, 0], [load, 0])

    def power(self, status):
        self.sr.output(self.highCurrent, status)
        return True    



class A4988:
    _direction = 1

    def __init__(self, directionpin, steppin, sleeppin, resetpin, ms3pin, ms2pin, ms1pin, enablepin, sr, revdir=False, ms=16, spr=200):
        self.directionpin = directionpin
        self.steppin = steppin
        self.sleeppin = sleeppin
        self.resetpin = resetpin
        self.ms3pin = ms3pin
        self.ms2pin = ms2pin
        self.ms1pin = ms1pin
        self.enablepin = enablepin
        self.revdir = revdir
        self.ms = ms
        self.spr = spr
        self.sr = sr
        
        # disable A4988 before setup
        self.sr.output([enablepin, 1], [resetpin, 0], [sleeppin, 0])
        
        # setting up MS
        mode = {1: '000', 2: '100', 4: '010', 8: '110', 16: '111'}
        self.sr.output([ms1pin, mode[ms][0]], [ms2pin, mode[ms][1]], [ms3pin, mode[ms][2]])
        
        # setting up GPIO outputs for direction and step 
        GPIO.setup(self.directionpin, GPIO.OUT)
        GPIO.setup(self.steppin, GPIO.OUT)

    def power(self, status):
        self.sr.output([self.enablepin, not status], [self.resetpin, status], [self.sleeppin, status])
        return True

    def move(self, steps, speed):  # speed - revolution per second
        t = 1.0/(self.spr*self.ms*speed)/2
        for i in range(abs(steps)):
            GPIO.output(self.steppin, True)
            sleep(t)
            GPIO.output(self.steppin, False)
            sleep(t)
            
    @property
    def direction(self):
        return self._direction

    @direction.setter
    def direction(self, value):
        self._direction = value
        if self.revdir:
            value = not value
        GPIO.output(self.directionpin, value)


class Servo:
    def __init__(self, pin, on=11, off=5):
        self.pin = pin
        GPIO.setup(pin, GPIO.OUT)

        self.pwm = GPIO.PWM(pin, 100)
        self.on = on
        self.off = off
        self.pwm.start(off)
        self.set(1)

    def set(self, status):
        if status:
            length = self.on
        else:
            length = self.off
        self.pwm.start(length)
        sleep(0.5)


class Plotter:
    m1, m2 = [0, 0], [76846, 0]
    spr = 200  # steps per revolution in full step mode
    ms = 16    # (1, 2, 4, 8, 16)
    length = (0, 0)
    calibrated = False
    right_engine, left_engine = None, None

    def __init__(self):
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        print("Initializing shift register")
        self.sr = ShiftRegister(15, 11, 13, 2)

        print("Initializing ATX power supply")
        self.power = ATX(7, 15, self.sr)


        print("Initializing left engine...")
        self.left_engine = A4988(26, 24, 14, 13, 12, 11, 10, 9, self.sr, True)
        print("Initializing right engine...")
        self.right_engine = A4988(18, 16, 6, 5, 4, 3, 2, 1, self.sr)

        print("Initializing separator...")
        self.separator = Servo(23)
        
        print("Turning power and motors on...")
        self.power.power(True)
        #self.power.load(True)
        self.left_engine.power(True)
        self.right_engine.power(True)

    def move_vertical(self, steps, speed):
        if sign(steps) == 1:
            self.left_engine.direction = 1
            self.right_engine.direction = 1
        else:
            self.left_engine.direction = 0
            self.right_engine.direction = 0

        speed *= 2
        for i in range(abs(int(steps))):
            self.left_engine.move(1, speed)
            self.right_engine.move(1, speed)

    def move_horizontal(self, steps, speed):
        if sign(steps) == 1:
            self.left_engine.direction = 1
            self.right_engine.direction = 0
        else:
            self.left_engine.direction = 0
            self.right_engine.direction = 1

        speed *= 2
        for i in range(abs(int(steps))):
            self.left_engine.move(1, speed)
            self.right_engine.move(1, speed)

    def move_both(self, left, right, speed):
        gleft = int(left)
        gright = int(right)
        if gleft == 0 or gright == 0:
            # move
            self.left_engine.move(gleft, float(speed))
            self.right_engine.move(gright, float(speed))
        else:
            rel = abs(float(gleft)/gright)
            # print(rel)
            done = 0
            ldir = sign(gleft)  # Left Direction
            rdir = sign(gright)  # Right Direction
            print(ldir)
            print(rdir)
            for i in range(1, abs(gright)+1):
                # print('R')
                self.right_engine.move(rdir, float(speed))
                htbd = int(i*rel)  # steps which Has To Be Done
                td = htbd - done  # steps To Do
                # print('L ' + str(td))
                self.left_engine.move(ldir*td, float(speed))
                done = htbd

    def goto(self, x, y, speed):
        if not self.calibrated:
            raise NotCalibratedError()
        raise NotImplementedError()

    def calibrate(self, x, y):
        self.length = ctl((int(x), int(y)), self.m1, self.m2)
        self.calibrated = True

    def exec(self, command):
        part = command.split(' ')
        if part[0] == 'L' or part[0] == 'R':
            if part[0] == 'L':
                mot = self.left_engine
            else:
                mot = self.right_engine

            if sign(int(part[1])) == 1:
                mot.direction = 1
            else:
                mot.direction = 0

            mot.move(int(part[1]), float(part[2]))
        elif part[0] == 'V':
            self.move_vertical(int(part[1]), float(part[2]))
        elif part[0] == 'H':
            self.move_horizontal(int(part[1]), float(part[2]))
        elif part[0] == 'S':
            self.separator.set(int(part[1]))
        elif part[0] == 'P':
            sleep(float(part[1]))
        elif part[0] == 'B':
            self.move_both(int(part[1]), int(part[2]), float(part[3]))
        elif part[0] == 'C':
            self.calibrate(int(part[1]), int(part[2]))
            return self.length
        elif part[0] == 'COR':
            if self.calibrated:
                return ltc(len, self.m1, self.m2)
            else:
                raise NotCalibratedError()
        elif part[0] == 'LEN':
            return self.length
        elif part[0] == 'GOTO':  # Actually move to spec. position
            if self.calibrated:
                self.goto(part[1], part[2], part[3])
            else:
                raise NotCalibratedError()
        elif part[0] == 'E':
            #GASIMY
            self.left_engine.power(False)
            self.right_engine.power(False)
            self.power.power(False)
            #self.power.load(False)
            exit()
        else:
            raise BadCommandError()
        return ""
