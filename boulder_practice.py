"""Invulnerable, playable boulder trap. python boulder_practice.py [--smoke]."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import struct
import time
from transitions import Machine

ROOT=Path(os.environ.get('MAZE_PROJECT',Path(__file__).resolve().parent))
ASSETS=ROOT/'sprite/traps/boulder_chase_v1'
OUTPUT=Path(os.environ.get('BOULDER_OUTPUT',ROOT/'output/boulder_practice'))
LENGTH=52.0
HALF_WIDTH=1.8
RADIUS=1.35
PLAYER_RADIUS=.19
# x, forward metres, half width, half depth. Each leaves a walkable side.
OBSTACLES=(('fallen_column',-.78,11,.60,.28),('rubble',.72,21,.49,.34),
           ('fallen_column',-.62,31,.60,.28),('rubble',.72,39,.49,.34))
EXITS=(('narrow',-1,46,.38),('wide',1,52,.70))


class Practice:
    """Metre-based rules, independent of rendering. Contact counts, never kills."""
    def __init__(self):
        Machine(model=self,states=['ready','chasing','clear'],initial='ready',auto_transitions=False,
                transitions=[['release','ready','chasing'],['finish',['ready','chasing'],'clear'],['restart','*','ready']])
        self.reset()

    def reset(self):
        self.restart()
        self.time=self.x=self.z=self.vx=self.vz=self.stride=0.0
        self.stamina=100.0
        self.hp=100
        self.ball_z=-3.0
        self.ball_speed=self.ball_distance=0.0
        self.contacts=0
        self.hit_until=self.notice_until=0.0
        self.look_back=self.blocked=self.running=False
        self.paused=False
        self.exit_used=None

    @property
    def gap(self):return self.z-self.ball_z-RADIUS-PLAYER_RADIUS

    @staticmethod
    def can_stand(x,z):
        return not any(abs(x-ox)<hw+PLAYER_RADIUS and abs(z-oz)<hd+PLAYER_RADIUS
                       for _,ox,oz,hw,hd in OBSTACLES)

    def exit_nearby(self):
        return next((name for name,side,z,half in EXITS if side*self.x>.65 and abs(self.z-z)<=half+.7),None)

    def use_exit(self):
        if self.state=='clear':return False
        name=self.exit_nearby()
        if name:
            self.exit_used=name
            self.finish()
            self.vx=self.vz=0
            return True
        return False

    def update(self,dt,dx=0,forward=0,sprint=False,look_back=False):
        dt=max(0,min(.05,dt))
        self.look_back=look_back
        if self.state=='clear' or not dt:return
        self.time+=dt
        if self.state=='ready' and self.time>=5:self.release()
        # Pushing along a side wall should not waste forward velocity.
        if abs(self.x)>=1.47 and dx*self.x>0:dx=0
        magnitude=math.hypot(dx,forward)
        fraction=min(1,self.stamina/(25*dt)) if sprint and magnitude else 0
        speed=2.55+(4.70-2.55)*fraction
        tx,tz=(dx/magnitude*speed,forward/magnitude*speed) if magnitude else (0,0)
        self.vx+=max(-15*dt,min(15*dt,tx-self.vx))
        self.vz+=max(-15*dt,min(15*dt,tz-self.vz))
        old_x,old_z=self.x,self.z
        nx=max(-1.48,min(1.48,self.x+self.vx*dt))
        nz=max(0,min(LENGTH+1.2,self.z+self.vz*dt))
        self.blocked=False
        if self.can_stand(nx,self.z):self.x=nx
        else:self.vx=0;self.blocked=True
        if self.can_stand(self.x,nz):self.z=nz
        else:self.vz=0;self.blocked=True
        travelled=math.hypot(self.x-old_x,self.z-old_z)
        self.stride+=travelled
        self.running=bool(fraction and travelled>.0001)
        if self.running:self.stamina=max(0,self.stamina-25*dt*fraction)
        if self.state=='chasing':
            self.ball_speed=min(3.7,self.ball_speed+1.8*dt)
            movement=self.ball_speed*dt
            self.ball_z+=movement
            self.ball_distance+=movement
            if self.gap<=0:
                self.contacts+=1
                self.hit_until=self.time+.45
                self.notice_until=self.time+2.2
                # Practice-only: retain player position/resources, put the rock
                # behind again so contact never becomes a death/soft-lock.
                self.ball_z=self.z-RADIUS-PLAYER_RADIUS-8
        for name,side,z,half in EXITS:
            if side*self.x>1.32 and abs(self.z-z)<half:
                self.exit_used=name;self.finish();self.vx=self.vz=0
                break
