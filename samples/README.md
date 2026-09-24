# samples

체크리스트(`scripts/checklist/run.sh`)가 임시 폴더에 복사해 프로젝트로 등록하는 샘플 프로젝트 셋이다.
원본은 고치지 않는다. `.madang/`은 등록할 때 core가 만든다.

| 폴더 | 종류 | 쓰는 곳 |
|---|---|---|
| `wiki/` | 위키 볼트(git 아님). `notes/`의 노트를 폴더 대상으로 게시한다 | 노트에 요청 → 게시 반영 |
| `code/` | 파이썬 코드(복사본을 git 저장소로 만든다). `word_count`에 버그가 있고 테스트가 그것을 잡는다 | 버그 수정 → 테스트 → 자동 머지 → 되돌리기 |
| `resume/` | 이력서 문서(git 아님). `docs/resume.md`가 `resume/basic` 뷰어로 `docs/resume.json`을 그린다 | 데이터 수정 → 문서 탭과 게시 화면 비교 |
