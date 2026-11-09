"""Rules + complete-course checks: python check_boulder_practice.py."""
import json
from boulder_practice import Practice,OBSTACLES,OUTPUT

def steps(g,seconds,**inputs):
    for _ in range(round(seconds/.02)):g.update(.02,**inputs)

def route(sprint_style,exit_name):
    g=Practice()
    for _ in range(4000):
        pending=[o for o in OBSTACLES if g.z<o[2]+o[4]+.3]
        target=(-.85 if pending[0][1]>0 else .85) if pending else (-1 if exit_name=='narrow' else 1)
        dx=1 if g.x<target-.045 else -1 if g.x>target+.045 else 0
        sprint=sprint_style=='held' or sprint_style=='timed' and g.gap<6
        g.update(.02,dx,1,sprint)
        if g.exit_nearby()==exit_name:g.use_exit()
        if g.state=='clear':break
    assert g.state=='clear' and g.exit_used==exit_name
    return {'exit':g.exit_used,'time':round(g.time,2),'contacts':g.contacts,'stamina':round(g.stamina,2)}

def main():
    g=Practice();steps(g,4.9)
    assert g.state=='ready' and g.ball_z==-3
    steps(g,.2);assert g.state=='chasing' and g.ball_z>-3
    steps(g,60);assert g.hp==100 and g.contacts>=8 and g.state=='chasing'
    stationary_contacts=g.contacts
    g.reset();g.x=1.35;steps(g,4.5,forward=1,sprint=True)
    assert g.stamina==0 and g.hp==100
    before=g.z;steps(g,.5,forward=1,sprint=True)
    assert g.z>before and g.stamina==0,'empty stamina must still permit walking'
    g.reset();g.x=-.78;g.z=9.9;steps(g,1.2,forward=1)
    assert g.z<10.53,'walked through solid column'
    steps(g,1,dx=1);steps(g,1.5,forward=1)
    assert g.z>11.6,'could not walk around column'
    g.reset();g.x,g.z=-1,46
    assert g.use_exit() and g.exit_used=='narrow' and g.state=='clear'
    g.reset();g.x,g.z=1,52
    assert g.use_exit() and g.exit_used=='wide'
    g.reset();steps(g,.2,dx=1,look_back=True)
    assert g.x>0 and g.look_back,'rear view should not invert input'
    routes=[route(style,exit_name) for style in ('walk','timed','held') for exit_name in ('narrow','wide')]
    assert routes[2]['contacts']<routes[0]['contacts'],'timed sprint did not improve this fixed reference route'
    assert routes[2]['stamina']>routes[4]['stamina'],'timed sprint did not preserve resources against held sprint'
    report={'passed':True,'stationary_60s_contacts_survived':stationary_contacts,'empty_stamina_walks':True,
            'obstacle_collision_and_bypass':True,'both_exits_reachable':True,'rear_view_preserves_input':True,
            'routes':routes,'note':'Reference steering routes, not a complete balance or human playtest.'}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'rules_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
