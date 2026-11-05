# gitsyncer

Linux와 Android Termux에서 여러 Git 저장소를 관리하는 터미널 도구입니다. 저장소 경로를 등록하고 상태를 조회하거나, 특정 저장소 또는 전체 저장소를 이름순으로 pull·push할 수 있습니다.

`gitsyncer`와 `깃싱커`는 같은 프로그램을 실행합니다. 터미널의 메뉴·도움말·입력 안내·오류 메시지는 영문입니다.

## 설치

Python 3.9 이상과 Git이 필요합니다. 셸 자동완성은 Bash·Zsh를 지원하며, 별도 Python 패키지는 필요하지 않습니다. Termux에서는 먼저 해당 환경의 패키지 관리자로 Python과 Git을 준비하세요.

프로젝트 폴더에서 실행합니다.

```sh
sh install.sh
```

실행 파일은 `~/.local/bin/`, 프로그램 본체는 `~/.local/share/gitsyncer/`에 설치됩니다. 관리자 권한은 필요하지 않습니다.

설치기는 `.bashrc`와 `${ZDOTDIR:-$HOME}/.zshrc`에 PATH·자동완성 설정을 추가합니다. 변경 전 파일을 백업하며, 재설치해도 설정 블록을 중복 추가하지 않습니다. 설치 후 새 터미널을 열면 적용됩니다.

셸 설정을 직접 관리하려면 다음 옵션을 사용하세요.

```sh
sh install.sh --no-shell-setup
```

업데이트도 `sh install.sh`로 수행합니다. 등록한 저장소 목록은 보존됩니다.

## 사용법

```sh
gitsyncer status                    # 저장소 목록과 등록·삭제 메뉴
gitsyncer status --no-interactive   # 목록 출력 후 종료
gitsyncer add ~/workspace/project  # 경로 등록
gitsyncer add                      # 경로 입력창 열기
gitsyncer status add               # status에서 경로 등록
gitsyncer remove project           # 등록만 삭제, 실제 폴더 유지
gitsyncer pull all                 # 전체 저장소 fetch·pull
gitsyncer pull project             # 특정 저장소 fetch·pull
gitsyncer push all                 # 전체 저장소의 변경·미전송 커밋 처리
gitsyncer push project             # 특정 저장소 commit·push
```

한글 별칭도 동일하게 사용할 수 있습니다. 예: `깃싱커 push all`.

`status`의 대화형 메뉴에서 `a`는 등록, `d`는 등록 삭제, `r`은 새로고침, Enter 또는 `q`는 종료입니다. 터미널이 아닌 환경에서는 목록만 출력하고 종료합니다.

## 자동완성과 저장소 등록

- `gitsyncer` 뒤에 공백을 입력하고 Tab을 누르면 명령 목록이 표시됩니다.
- `pull`, `push`, `remove` 뒤에서는 등록된 저장소 이름을 완성합니다.
- `add` 뒤와 대화형 경로 입력창에서는 Tab으로 경로를 완성할 수 있습니다. 공백이 포함된 경로도 지원합니다.
- 저장소 이름은 실제 Git 루트 경로의 마지막 폴더명입니다. 하위 폴더를 지정해도 Git 루트를 등록합니다.
- 같은 이름으로 다른 경로를 중복 등록할 수 없습니다. 이런 경우 폴더명을 구분해야 합니다. `all`은 전체 선택용 예약 이름입니다.

## Pull 동작

`fetch --prune` 후 `pull --ff-only --no-rebase --no-autostash`를 실행합니다.

로컬 변경, 미해결 충돌, detached HEAD, 진행 중인 merge·rebase가 있으면 해당 저장소를 처리하지 않습니다. 브랜치가 서로 갈라져 fast-forward가 불가능하면 직접 해결하도록 오류를 표시합니다. 변경 사항을 자동으로 stash하거나 버리지 않습니다.

## Push 동작

변경된 저장소는 `git status --short`로 변경 목록을 보여주고 커밋 메시지를 입력받습니다. 메시지를 입력하면 저장소 루트에서 `git add .` → commit → push 순서로 처리합니다. Git의 ignore 규칙은 그대로 적용됩니다.

메시지를 비우면 staging을 바꾸지 않고 해당 저장소를 건너뜁니다. Ctrl+C 또는 입력 종료(EOF)는 전체 작업을 취소합니다.

`push all`은 저장소 이름순으로 처리합니다. 로컬 변경과 미전송 커밋이 없으면 건너뛰며, 이미 커밋된 미전송 작업은 새 커밋 없이 push합니다. 추적 정보가 없는 저장소는 최초 push를 시도할 수 있습니다. push에 실패해도 생성한 커밋은 보존되며 force push는 사용하지 않습니다.

원격 대상은 현재 브랜치의 upstream을 따릅니다. upstream이 없으면 원격이 정확히 하나일 때 현재 브랜치 이름으로 전송합니다. 원격이 없거나 여러 개인 경우 대상을 추측하지 않고 오류를 표시합니다.

한 저장소가 실패해도 다음 저장소를 계속 처리하고 마지막에 실패 목록을 출력합니다. Git 인증과 훅은 기존 설정을 사용합니다. Git 표준 메시지는 C locale로 영문 출력하지만, 외부 인증 도구나 사용자 훅의 언어는 해당 도구가 결정합니다.

## 설정 파일

| 위치 | 용도 |
| --- | --- |
| `~/.local/bin/gitsyncer` | 기본 실행 명령 |
| `~/.local/bin/깃싱커` | 한글 실행 별칭 |
| `~/.local/share/gitsyncer/` | 프로그램 본체와 자동완성 파일 |
| `~/.config/gitsyncer/repos.json` | 기기별 저장소 등록 목록 |

등록 목록의 기본 위치는 `${XDG_CONFIG_HOME:-$HOME/.config}/gitsyncer/repos.json`입니다. `GITSYNCER_CONFIG` 환경변수로 다른 파일을 지정할 수 있습니다.

PC 경로와 Termux 경로는 다를 수 있으므로 각 기기의 실제 경로를 등록하세요. 이 도구는 없는 저장소를 clone하거나 등록 목록을 자동 동기화하지 않습니다.

## 상태 조회

상태표는 이름과 브랜치 등 각 열의 최대 표시 너비에 맞춰 정렬하며 한글 이름도 지원합니다. 터미널 너비보다 긴 행은 줄바꿈될 수 있습니다.

`status`는 네트워크에 접속하지 않습니다. ahead/behind 값은 로컬의 원격 추적 정보를 사용하므로 실제 원격 상태보다 오래된 값일 수 있습니다. 기기를 바꿔 작업할 때는 먼저 pull로 확인하세요.

등록 목록은 잠금과 원자적 파일 교체로 저장합니다. Git 명령은 셸 문자열 대신 인자 배열로 실행합니다. 저장소는 순차 처리하며 각각의 커밋 메시지를 입력받습니다. 하위 모듈 내부 변경은 상위 저장소의 `git add .`만으로 커밋되지 않습니다.

## 종료 코드

| 코드 | 의미 |
| --- | --- |
| `0` | 완료. 의도적 건너뛰기와 빈 목록 포함 |
| `1` | 등록 정보·파일시스템·Git 작업 오류 |
| `2` | 잘못된 명령 인자 |
| `130` | Ctrl+C 또는 EOF로 취소 |

## 개발 및 테스트

프로젝트 루트에서 실행합니다.

```sh
python3 -m unittest discover -s tests -v
```

Linux에서 14개 통합 테스트와 실제 터미널의 경로·명령 자동완성을 검증했습니다. Termux는 같은 설치 방식을 사용하지만 실제 휴대폰에서의 실행은 아직 검증하지 않았습니다.

## 삭제

두 실행 파일과 `~/.local/share/gitsyncer/`를 삭제하고, 셸 설정에서 `gitsyncer` 시작·끝 표시 사이의 블록을 제거합니다. 등록 목록을 보존하려면 설정 디렉터리는 남겨두세요.
