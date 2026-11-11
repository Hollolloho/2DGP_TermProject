# 초보자를 위한 미로 탈출 안내서

최신 기획은 `PRD.md`, 교체 에셋 규격·제작 목록은 `ASSET_TASKS.md`를 따른다.

## 현재 실행 범위

`feature/asset`에서 구형 에셋 참조를 정리했다. 이동·벽 충돌·시야·샘물·방문 지도·정지 수호자 타격·1인칭 칼날방은 계속 검사할 수 있다.

현재 일반 미로의 좌표와 카메라는 **탑뷰 검사용**이다. 새 플레이어는 대기 프레임을 사용하며, 쿼터뷰 지형 배치·깊이 가림·카메라와 5상태 애니메이션 연결은 다음 단계다. 새 그림이 준비됐다는 이유만으로 쿼터뷰 전환이 끝난 것은 아니다.

지형은 쿼터뷰 좌표 전환 전까지 기존 석재 재질의 사각 격자로 표시한다. 수호자·샘물·입구의 새 카탈로그가 없으면 개발용 도형을 사용한다. 돌 연습의 장애물과 출구도 충돌 범위에 맞춘 석재 도형으로 표시한다. 완성 그래픽이나 최종 미술 검토용 화면이 아니다. 사물 카탈로그가 준비되면 다음 실행부터 새 파일을 읽으며, 쿼터뷰 지형 시트의 실제 배치는 다음 단계에서 연결한다.

## 실행

Python과 `requirements.txt`의 pico2d·transitions가 필요하다. Windows 맑은 고딕을 사용한다.

```powershell
python -m pip install -r requirements.txt
python main.py
python boulder_practice.py
```

일반 미로 창은 1280×800, 내부 화면은 640×400이다. `--overview`는 전체 미로 검사, `--trap-preview`는 칼날방 이동 검사에 사용한다.

| 입력 | 현재 동작 |
| --- | --- |
| WASD / 방향키 | 일반 미로에서 화면 기준 상하좌우 이동 |
| Shift + 이동 | 달리기·스태미너 소모 |
| 마우스 좌클릭 | 검격 효과·가까운 수호자 타격 |
| F | 횃불·샘물·함정방·중앙 탈출구 상호작용 |
| M | 방문 지도. 세계 시간은 계속 진행 |
| V | 전체 미로 검사 보기 전환 |
| R | 새 회차·스폰 변경·시작 시간대 낮→밤→새벽 순환 |
| F10 | `output/topdown/manual.png` 저장 |
| Esc | 지도 닫기 / 함정방 원위치 복귀 / 탐색 중 종료 |
| 함정방 W/S, A/D | 전진·후진, 좌우 회피 |

Space 회피·몬스터 AI·시간대별 지형 변형·실제 퍼즐과 예약 개방·최종 사망·로프 상승 엔딩은 후속 구현이다. 현재 60초 조명 전환과 HP 0 시 체력 초기화·입구 복귀는 시제품 규칙이다. 독립 돌 연습의 무적도 최종 즉사 규칙과 구분한다.

## 에셋 연결

- `sprite/quarter/player_explorer_v1`: 기존 완성 플레이어와 JSON.
- 새 지형·소품·수호자·숏컷: `ASSET_TASKS.md`의 경로와 `catalog.json`으로 연결한다.
- 돌방 사물: `sprite/traps/boulder_room_v2/catalog.json`의 `props`·`exits`를 읽는다.
- `sprite/traps/boulder_chase_v1/catalog.json`은 **먼지 전용**이다.
- 1인칭 벽·바닥·천장 원본 재질, 회전 돌 재질, 칼날, 불꽃·검격 효과, 효과음은 재사용한다.
- 삭제된 시트의 재패킹 도구와 구형 돌 비교용 복사 코드는 제거했다. 에셋 제작용 도구는 각 새 에셋 폴더에서 관리한다.

## 검사

다음 명령은 창을 조작하지 않고 실행된다. 화면 검사는 SDL dummy renderer를 사용한다.

```powershell
python checks_assets.py
python checks_topdown.py
python check_boulder_practice.py
python main.py --smoke
python boulder_practice.py --smoke --width 1280 --height 800
python sprite/traps/boulder_volume_v2/tools/check_visuals.py
```

`checks_assets.py`는 재사용 파일·프레임 좌표·발 기준점·출구 개구부와 준비/미완료 묶음을 확인한다. `--require-complete`를 붙이면 제작 중인 에셋이 하나라도 있을 때 실패한다.

규칙 검사는 32개 미로의 연결성·충돌·복귀, 돌 연습의 이동·접촉·스태미너·출구를 확인한다. 화면 검사는 실제 입력 처리와 새 에셋/임시 표시 경로를 확인한다. `output/` 결과는 Git에서 제외한다. 이 결과가 최종 쿼터뷰의 가림·가독성·난도·성능 검증을 대신하지 않는다.
