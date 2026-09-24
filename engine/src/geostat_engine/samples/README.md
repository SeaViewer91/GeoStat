# 샘플 데이터

앱의 **도움말 → 샘플 데이터 열기**로 여는 연습용 자료임. `scripts/make_bundled_samples.py`로 만듦.

| 파일 | 내용 | 출처 |
|---|---|---|
| `georgia.gpkg` | 미국 조지아주 159개 카운티의 학사 학위 비율(PctBach)과 사회경제 변수 (1990). GWR·MGWR 연습용 | Fotheringham, Brunsdon & Charlton (2002) *Geographically Weighted Regression*. PySAL `libpysal.examples` (BSD-3) 배포본에 NAD83 UTM 17N 좌표계를 지정함 |
| `nc_sids.gpkg` | 미국 노스캐롤라이나 100개 카운티의 영아 돌연사(SIDS) 건수·비율 (1974–84). ESDA 연습용 | Cressie (1993) *Statistics for Spatial Data*. GeoDa Center·PySAL 배포본에 NAD27 경위도 좌표계를 지정해 WGS84로 변환함 |
| `seoul_grid.shp` | 서울 부근 500 m 가상 격자 900개. 인구·소득·녹지율은 공간 자기상관이 있게 만든 **가상 값**임. cp949 DBF(`.cpg` 없음) | 자체 생성 |
| `terrain.tif` | 서울 부근 25 m 가상 지형 (800×800). 존 통계·격자 집계 연습용 **가상 값**임 | 자체 생성 |
