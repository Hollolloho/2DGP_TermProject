"""Six adjacent transverse slopes and swept, repeating rock collisions."""
from dataclasses import dataclass
import math
from types import SimpleNamespace
from .first_person import turned_yaw, walk_velocity

LANE_COUNT, LANE_DEPTH, LANE_START = 6, 3., 3.
HALF_WIDTH, SLOPE = 5., .32
RADIUS, COLLISION_RADIUS = 1.35, 1.52
PLAYER_RADIUS, PLAYER_HEIGHT = .19, 1.7
WALK_SPEED, RUN_SPEED = 2.55, 4.70
BALL_SPEED = 2.15
ROLL_LIMIT = HALF_WIDTH+COLLISION_RADIUS+.5
CYCLE_SECONDS = 2*ROLL_LIMIT/BALL_SPEED
EXIT_Z = LENGTH = LANE_START+LANE_COUNT*LANE_DEPTH+3.
MAX_STEP_HEIGHT = .12
PASSAGE_HALF_WIDTH, BEVEL_DEPTH = 1.3, .85


def lane_at(z):
    if LANE_START <= z < LANE_START+LANE_COUNT*LANE_DEPTH:
        return int((z-LANE_START)//LANE_DEPTH)
    return None


def lane_slope(lane):
    return -SLOPE if lane % 2 == 0 else SLOPE


def connection_width(lane, z):
    """Half-width of the level wedge joining the opposing slopes."""
    if lane is None:
        return 0.
    start = LANE_START+lane*LANE_DEPTH
    edge_distance = max(0., min(z-start, start+LANE_DEPTH-z))
    return PASSAGE_HALF_WIDTH*max(0., 1.-edge_distance/BEVEL_DEPTH)


def row_height(lane, x, z):
    if lane is None:
        return 0.
    width = connection_width(lane, z)
    return lane_slope(lane)*math.copysign(max(0., abs(x)-width), x)


def floor_height(x, z):
    return row_height(lane_at(z), x, z)


@dataclass(frozen=True)
class Stone:
    lane: int
    x: float
    y: float
    z: float
    slope: float
    direction: int
    distance: float
    cycle: int
    radius: float = RADIUS
    speed: float = BALL_SPEED
    active: bool = True


def capsule_hit(start, end):
    """A moving sphere relative to an upright player capsule, over one segment."""
    delta = tuple(b-a for a,b in zip(start, end))
    low, high = PLAYER_RADIUS, PLAYER_HEIGHT-PLAYER_RADIUS
    candidates = [0., 1.]
    horizontal = delta[0]**2+delta[2]**2
    if horizontal:
        candidates.append(-(start[0]*delta[0]+start[2]*delta[2])/horizontal)
    total = sum(value*value for value in delta)
    for cap in (low, high):
        if total:
            candidates.append(-sum(a*b for a,b in zip(
                (start[0], start[1]-cap, start[2]), delta))/total)
        if delta[1]:
            candidates.append((cap-start[1])/delta[1])
    for fraction in candidates:
        t = max(0., min(1., fraction))
        x,y,z = (a+d*t for a,d in zip(start, delta))
        vertical = y-max(low, min(high, y))
        if x*x+vertical*vertical+z*z <= (COLLISION_RADIUS+PLAYER_RADIUS)**2:
            return True
    return False


class SixLaneTrap:
    def __init__(self, player=None):
        self.player = player if player is not None else SimpleNamespace(hp=100, stamina=100.)
        self.reset()

    @property
    def hp(self):
        return self.player.hp

    @hp.setter
    def hp(self, value):
        self.player.hp = value

    @property
    def stamina(self):
        return self.player.stamina

    @stamina.setter
    def stamina(self, value):
        self.player.stamina = value

    floor_height = staticmethod(floor_height)
    lane_at = staticmethod(lane_at)

    def reset(self):
        self.yaw = self.movement_yaw = 0.
        self.time = self.x = self.z = self.vx = self.vz = self.stride = 0.
        self.state = 'crossing'
        # 중앙 보행자의 각 줄 도착 시각에 돌은 양쪽 벽 바깥을 지나도록 맞춘다.
        self.phase_offsets = [-(LANE_START+(lane+.5)*LANE_DEPTH)/WALK_SPEED
                              for lane in range(LANE_COUNT)]
        self.contacts = 0
        self.ball_touching = self.blocked = self.running = False
        self.hit_until = 0.
        self.exit_used = None

    def turn(self, relative_x):
        self.yaw = turned_yaw(self.yaw, relative_x)

    def stone_at(self, lane, seconds, cycle=None):
        clock = seconds+self.phase_offsets[lane]
        cycle = math.floor(clock/CYCLE_SECONDS) if cycle is None else cycle
        age = clock-cycle*CYCLE_SECONDS
        direction = 1 if lane % 2 == 0 else -1
        slope = lane_slope(lane)
        x = direction*(-ROLL_LIMIT+BALL_SPEED*age)
        z = LANE_START+(lane+.5)*LANE_DEPTH
        y = row_height(lane,x,z)+RADIUS*math.sqrt(1+slope*slope)
        return Stone(lane, x, y, z,
                     slope, direction, BALL_SPEED*age*math.sqrt(1+slope*slope), cycle)

    @property
    def stones(self):
        return [self.stone_at(lane, self.time) for lane in range(LANE_COUNT)]

    @property
    def next_lane(self):
        return next((lane for lane in range(LANE_COUNT)
                     if LANE_START+(lane+.5)*LANE_DEPTH+COLLISION_RADIUS >= self.z), None)

    def _swept_contact(self, before, after, old_time, dt):
        cuts = {0., 1.}
        for offset in self.phase_offsets:
            wrap = (math.floor((old_time+offset)/CYCLE_SECONDS)+1)*CYCLE_SECONDS-offset
            if old_time < wrap < old_time+dt:
                cuts.add((wrap-old_time)/dt)
        dx, dz = after[0]-before[0], after[1]-before[1]
        if dz:
            first, last = sorted((before[1], after[1]))
            for boundary in range(LANE_COUNT+1):
                seam = LANE_START+boundary*LANE_DEPTH
                for z in (seam-BEVEL_DEPTH, seam, seam+BEVEL_DEPTH):
                    if first < z < last:
                        cuts.add((z-before[1])/dz)
        # Within each span the two edges of the level wedge are straight.
        # Split where the player's trajectory intersects either one.
        spans = sorted(cuts)
        for a,b in zip(spans, spans[1:]):
            lane = lane_at(before[1]+dz*(a+b)/2)
            for side in (-1, 1):
                left = before[0]+dx*a-side*connection_width(lane, before[1]+dz*a)
                right = before[0]+dx*b-side*connection_width(lane, before[1]+dz*b)
                if left*right < 0.:
                    cuts.add(a+(b-a)*left/(left-right))
        cuts = sorted(cuts)
        for a,b in zip(cuts, cuts[1:]):
            middle = (a+b)/2
            pz = before[1]+dz*middle
            lane = lane_at(pz)
            for index in range(LANE_COUNT):
                center = LANE_START+(index+.5)*LANE_DEPTH
                if abs(center-pz) > COLLISION_RADIUS+PLAYER_RADIUS+abs(dz)*(b-a)/2:
                    continue
                cycle = math.floor((old_time+dt*middle+self.phase_offsets[index])/CYCLE_SECONDS)
                relative = []
                for fraction in (a,b):
                    x = before[0]+(after[0]-before[0])*fraction
                    z = before[1]+(after[1]-before[1])*fraction
                    stone = self.stone_at(index, old_time+dt*fraction, cycle)
                    relative.append((stone.x-x, stone.y-row_height(lane,x,z), stone.z-z))
                if capsule_hit(*relative):
                    return True
        return False

    def advance(self, dt, dx=0, forward=0, sprint_fraction=0):
        dt = max(0., min(.05, dt))
        if self.state == 'clear' or not dt:
            return
        before = self.x, self.z
        old_time = self.time
        self.time += dt
        speed = WALK_SPEED+(RUN_SPEED-WALK_SPEED)*sprint_fraction
        self.vx,self.vz = walk_velocity(dx, forward, self.yaw, self.movement_yaw,
                                        self.vx, self.vz, speed, 15., dt)
        self.movement_yaw = self.yaw
        self.x = max(-HALF_WIDTH+PLAYER_RADIUS, min(HALF_WIDTH-PLAYER_RADIUS, self.x+self.vx*dt))
        target_z = max(0., min(EXIT_Z, self.z+self.vz*dt))
        self.blocked = False
        for index in range(LANE_COUNT+1):
            boundary = LANE_START+index*LANE_DEPTH
            if min(self.z, target_z) < boundary <= max(self.z, target_z):
                fraction = (boundary-self.z)/(target_z-self.z)
                crossing_x = before[0]+(self.x-before[0])*fraction
                heights = (floor_height(crossing_x, boundary-1e-6), floor_height(crossing_x, boundary+1e-6))
                if abs(heights[0]-heights[1]) > MAX_STEP_HEIGHT:
                    target_z = boundary-math.copysign(1e-6, self.vz)
                    self.vz = 0.
                    self.blocked = True
                    break
        self.z = target_z
        travelled = math.hypot(self.x-before[0], self.z-before[1])
        self.stride += travelled
        self.running = bool(sprint_fraction and travelled > .0001)
        touching = self._swept_contact(before, (self.x, self.z), old_time, dt)
        if touching and not self.ball_touching:
            self.contacts += 1
            self.hit_until = self.time+.45
        self.ball_touching = touching

    def exit_nearby(self):
        return 'front' if self.z >= EXIT_Z-.8 and abs(self.x) <= PASSAGE_HALF_WIDTH else None

    def use_exit(self):
        if self.exit_nearby():
            self.exit_used = 'front'
            self.state = 'clear'
            self.vx = self.vz = 0.
            return True
        return False

    def automatic_exit(self):
        return self.use_exit() if self.z >= EXIT_Z else False
