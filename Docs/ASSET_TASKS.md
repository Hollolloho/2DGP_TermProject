# 교체 에셋 제작 목록

2026-11-15 구현 기준으로 [PRD](PRD.md)와 대조했다.

일반 미로는 쿼터뷰 지형·캐릭터 시트를 사용한다. 칼날방과 별도 돌 추격 연습은 원본 석재를 투영한 1인칭 복도를 사용한다. 칼날방은 정면 시점을 고정하고, 돌 연습은 Q를 누르는 동안 후방을 보여 준다. 새 에셋은 기존 플레이어의 페인팅 스타일과 석재 재질에 맞춰 제작한다.

## 게임 연결 상태

| 묶음 | 게임 파일 | 현재 연결 |
| --- | --- | --- |
| 쿼터뷰 지형 | `sprite/quarter/terrain_v1/terrain.png`, `catalog.json` | 일반 미로의 바닥 4종, 연결 벽 16종, 시야 페이드와 시간대별 벽 전환에 사용 |
| 쿼터뷰 소품 | `sprite/quarter/props_v1/props.png`, `catalog.json` | 샘물 사용 전후, 좌우 벽 부착 횃불의 획득 전후, 중앙 로프 탈출구 표시 |
| 쿼터뷰 숏컷 | `sprite/quarter/shortcuts_v1/shortcuts.png`, `catalog.json` | 닫힌 문과 개방된 문, 칼날방 입구 A와 도착점 B에 방향별 프레임 사용 |
| 수호자 | `sprite/quarter/guardian_v1/guardian.png`, `catalog.json` | 추적과 공격 중에도 이동·공격 방향에 맞는 대기 자세 사용. 머리 위에 공격 예고와 HP 표시 |
| 플레이어 | `sprite/quarter/player_explorer_attack_v2/explorer.png`, `explorer.json`, `moving-attack.png` | 8방향 대기·걷기·단검 2연타, 대각선 4방향 달리기, 이동 공격의 상·하체 합성 |
| 마우스 미로 | `sprite/ui/mouse-maze-panel.png`, 공용 벽·바닥 재질 | 석재 패널 위에 9×5 미로와 현재·다음 시간대의 국소 문 미리보기를 그린다. 커서를 따라 연결선과 골드 톤의 경로 바닥을 갱신한다. |
| 1인칭 돌방 | `sprite/traps/boulder_room_v2/obstacles.png`, `exits.png`, `catalog.json` | 별도 돌 추격 연습에 쓰러진 기둥·돌무더기, 좁은/넓은 측면 출구 사용 |

수호자의 걷기·공격·피격 전용 애니메이션, 플레이어 회피와 로프 상승 엔딩 애니메이션, 마우스 미로 이외 퍼즐의 UI는 후속 제작이다. 돌 함정의 본 게임 연결도 후속 작업이다.

## 공통 제작 규격

- 현재 플레이어 `sprite/quarter/player_explorer_attack_v2/explorer.png`를 시점·색감·크기의 기준으로 사용한다. 프레임은 64×64 RGBA이고 발 기준점은 (32,54)다.
- 투명 PNG, 외곽에 배경색 테두리 없음. 검토용 배경·문자·격자선은 결과 시트에 넣지 않는다.
- 게임 내부 논리 크기 기준으로 제작하고 정수 2배 확대를 확인한다. 게임용 시트와 별도 미리보기를 구분한다.
- 쿼터뷰 격자의 N, E, S, W는 화면의 북동, 남동, 남서, 북서에 각각 대응한다. 방향마다 원근과 조명에 맞춰 제작한다.
- JSON 좌표는 좌상단 기준이다. 각 프레임은 `rect: [x,y,w,h]`, 프레임 안의 지면 기준점 `pivot: [x,y]`를 가진다.
- 지형·소품·숏컷·수호자 카탈로그 공통 형태는 `{"image":"파일명.png","frames":{"이름":{"rect":[0,0,64,64],"pivot":[32,54]}}}`다. 실제 시트 크기와 메타데이터를 검사한다.
- 런타임 시트와 카탈로그, 인계에 필요한 편집 원본과 출처를 보관한다. 검토용 미리보기와 임시 출력은 검증 뒤 정리한다.

### 1. 지형

- `floor_0`~`floor_3`: 64×32 마름모 판석 바닥. pivot (32,16). 이음새가 자연스럽게 이어지고 캐릭터보다 명암 대비를 낮춘다.
- `wall_0`~`wall_15`: 64×96 프레임, 지면 중심 pivot (32,80). 바닥 점유는 64×32 마름모이며 벽의 높이·광원은 공통이다.
- 번호는 연결 비트 N=1, E=2, S=4, W=8의 합이다. 0은 독립 기둥, 1방향은 끝면, 2방향은 직선/모퉁이, 3방향은 분기, 15는 네 방향 연결이다.
- 벽 윗면·옆면·끝면을 구분하고 연결된 면은 맞닿아야 한다. 임의의 바닥 배경을 벽 프레임에 붙이지 않는다.
- 지형을 바꿀 때는 현재 플레이어와 바닥·직선 벽·모퉁이 벽을 함께 배치해 크기와 가림 순서를 검토한다.

### 2. 소품

- `fountain_full`, `fountain_empty`, `rope_exit`는 64×96, 지면 중심 pivot (32,80)을 사용한다. 샘물의 물과 빛으로 사용 가능·고갈을 구분하고, 중앙 탈출구는 위에서 내려온 줄과 지면의 빛으로 표시한다.
- 벽 횃불은 `torch_wall_left_full`, `torch_wall_right_full`, `torch_wall_left_empty`, `torch_wall_right_empty`의 32×48 프레임을 사용한다. 좌측 pivot은 (19,31), 우측은 (13,31)이며 획득 전후에도 그대로다.
- 불꽃은 획득 전 프레임의 `wick_anchor`에 따로 합성한다. 획득 뒤에는 빈 받침을 그리고 불꽃을 플레이어 가방의 장착점으로 옮긴다.

### 3. 숏컷

- 키: `puzzle_closed_south`, `puzzle_open_south`, `trap_entry_south`, `trap_arrival_south`. 각 상태에 `south/east/north/west` 4개 격자 방향을 제공한다.
- 기본 128×128, 문턱 중앙 pivot (64,96). 시트의 상태별 크기·문턱 위치를 맞춘다.
- 퍼즐형: 문양·작은 돌 버튼이 있는 아치 돌문. 함정형: 무너진 석벽 틈. 주변 지형을 덮는 사각 배경은 넣지 않는다.
- 방향 이름은 기존 격자 면을 뜻한다. 화면 방향은 공통 규격의 쿼터뷰 대응을 따른다.

### 4. 수호자

- 키: `idle_sw`, `idle_nw`, `idle_se`, `idle_ne`.
- 프레임 64×64, pivot (32,54). 새 플레이어 옆에서 같은 지면에 서게 한다.
- 현재 한 종류를 운용하며 추적·공격 방향을 이 네 자세로 표시한다. `!` 예고와 체력 막대는 화면 코드에서 그린다.

### 5. 돌방 장애물·출구

- 이 묶음은 독립 돌 연습의 1인칭 복도용이다. 기존 벽·바닥 재질과 회전 돌의 색감에 맞춘다.
- `catalog.json`의 `props`에 `fallen_column`, `rubble`, `exits`에 `narrow`, `wide`를 둔다.
- 각 항목: `image`, `rect_top_left`, `pivot`, `world_frame_size_metres`. 출구는 여기에 `opening_uv: [left,top,right,bottom]`을 넣어 실제 투명 개구부를 명시한다. UV는 해당 프레임 안의 0~1 값이다.
- 장애물 프레임은 1024×512다. 기둥은 1.28×0.64m, 돌무더기는 1.164×0.582m로 표시한다. 바닥 접점과 투명 여백을 카탈로그에 기록한다.
- 출구 프레임은 768×1024이고 1.67×2.23m로 표시한다. 좁은/넓은 출구의 투명 개구부를 통해 안쪽 통로를 그린다.
- 충돌·이동·출구 조건은 기존 모델을 유지한다. 제작 편의를 위해 게임 규칙을 바꾸지 않는다.

## 플레이어와 재사용 에셋

- 현재 플레이어 파일의 달리기 클립은 대각선 4방향이다. 화면 상하좌우로 달릴 때는 가까운 대각선 클립을 사용한다. 피격 프레임은 시트에 들어 있으며 전용 피격 재생은 후속 작업이다. 레이어·검격·Spine 편집 자료는 [단검 애니메이션 인계서](../sprite/quarter/player_explorer_attack_v2/HANDOFF.md)를 참고한다.
- `sprite/quarter/player_explorer_v1`은 기존 플레이어 제작 자료로 보관한다. 게임은 `player_explorer_attack_v2` 시트를 읽는다.
- `sprite/wall/materials/base_a.png`, `sprite/surfaces/materials/floor_flagstone.png`, `sprite/surfaces/materials/ceiling_damp.png`는 1인칭 벽·바닥·천장 재질이다. 벽과 바닥은 마우스 미로 타일에도 사용한다.
- `sprite/traps/iron_blade.png`: 칼날.
- `sprite/traps/boulder_volume_v2/stone_material.png`, [`BoulderPractice/boulder_volume.py`](../BoulderPractice/boulder_volume.py): 회전 돌 재질·표현.
- `sprite/traps/boulder_chase_v1/dust.png`, 해당 `catalog.json`의 `dust`: 먼지 전용.
- `sprite/topdown/effects/torch.png`와 `torch.json`은 벽 횃불과 플레이어 가방의 불꽃이다. 8방향 검격은 `sprite/quarter/effects/dagger-slash.png`와 `dagger-slash.json`을 사용한다. 검격 출처는 [CREDITS.txt](../sprite/quarter/effects/CREDITS.txt), PIXELFX 라이선스는 [PIXELFX_LICENSE.txt](../sprite/topdown/PIXELFX_LICENSE.txt)에 있다.
- `sound/stone_step.wav`, `sound/blade_pass.wav`는 칼날방 효과와 시간대 전환 예고·연출에 사용한다.

## 연결과 검증

- [`SourceCode/game_view.py`](../SourceCode/game_view.py)는 일반 미로의 시트와 카탈로그를 시작 시 읽고 격자 좌표를 쿼터뷰로 투영한다. 벽·소품·캐릭터의 지면 기준점으로 가림 순서를 계산한다.
- [`BoulderPractice/boulder_practice.py`](../BoulderPractice/boulder_practice.py)는 먼지와 장애물·출구 카탈로그를 각각 읽어 별도 연습 화면에 사용한다.
- 저장소 루트에서 `python -m TestCode.checks_assets --require-complete`로 현재 시트·카탈로그의 프레임 좌표, 발 기준점, 횃불 장착점, 단검 타격 시점, 출구 개구부를 검사한다. `python -m SourceCode.main --smoke`는 로딩·화면 표시와 실제 입력 경로를 검사한다.
- 에셋 채팅은 제작을, 코딩 채팅은 게임 연결을, 기획 채팅은 기획·발표 자료를 담당한다. 총괄 채팅에서 연결 결과를 검증한다.
