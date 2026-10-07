# 월드 브리핑

해외 주요 매체의 헤드라인을 날짜별로 모아 보여 주고, 원화 환율을 함께 보여 주는 정적 뉴스 페이지입니다.
서버가 없어서 GitHub Pages에 올리면 폰에서 LTE로도 열립니다.

## 동작 방식

1. GitHub Actions가 1시간마다 `scripts/fetch_news.py`를 실행합니다.
2. 스크립트가 `feeds.json`에 적힌 RSS와 환율 API(Frankfurter)를 읽어 `data/` 아래 JSON으로 저장합니다.
3. `index.html`이 그 JSON을 읽어 화면을 그립니다. API 키는 필요 없습니다.

## 처음 올리는 방법

1. github.com에서 새 저장소를 만듭니다. 이름은 `world-news`, 공개(Public)로 설정합니다.
2. 이 폴더에서 아래를 실행합니다. `내아이디`는 본인 GitHub 아이디로 바꿉니다.
   ```bash
   cd ~/Desktop/벨런스게임_외부작동/world-news
   mkdir -p .github/workflows && mv update.yml .github/workflows/update.yml
   git init
   git add .
   git commit -m "월드 브리핑 첫 버전"
   git branch -M main
   git remote add origin https://github.com/내아이디/world-news.git
   git push -u origin main
   ```
3. 저장소 Settings → Pages → Branch를 `main` / `/ (root)`로 지정하고 Save를 누릅니다.
4. 저장소 Actions 탭 → 왼쪽 ‘뉴스 갱신’ → Run workflow를 눌러 첫 수집을 돌립니다. 1~2분 걸립니다.
5. `https://내아이디.github.io/world-news/`를 엽니다. 이후에는 1시간마다 자동으로 갱신됩니다.

처음 열었을 때 기사가 없다는 안내가 나오면 4번을 아직 안 한 것입니다.
화면 모양만 먼저 보고 싶으면 주소 끝에 `?demo=1`을 붙이세요. 가짜 데모 데이터가 나옵니다.

## 알아 둘 점

- 날짜별 기록은 첫 수집일부터 쌓입니다. RSS는 최근 기사만 주기 때문에 과거 날짜는 채울 수 없습니다.
- 매체 RSS 주소는 바뀌거나 막힐 수 있습니다. 응답하지 않은 피드는 건너뛰며, 화면 맨 아래에 응답한 매체가 표시됩니다.
- 공개 저장소에서 60일 동안 활동이 없으면 GitHub이 자동 실행을 멈출 수 있습니다. 화면 위에 "수집이 멈춘 것 같아요" 안내가 뜨면 Actions 탭에서 워크플로를 다시 켜 주세요.
- Actions 실행에서 push가 거절(403)되면 Settings → Actions → General → Workflow permissions를 ‘Read and write permissions’로 바꿉니다.
- 환율은 중앙은행 기준 일일 참고값입니다. 실시간 시세가 아닙니다.
- 매체를 추가하거나 빼려면 `feeds.json`을 고칩니다. 분야(`cat`)는 world, business, asia, tech 중에서 고릅니다.
- 기사는 제목, 두 줄 요약, 원문 링크만 보여 줍니다. 저작권은 각 매체에 있습니다.
