// 자주 쓰는 좌표계 프리셋 (국내 자료 기준)

export interface CrsPreset {
  epsg: number;
  label: string;
}

export const CRS_PRESETS: CrsPreset[] = [
  { epsg: 5186, label: "Korea 2000 / 중부원점 (GRS80, 가산 60만)" },
  { epsg: 5179, label: "Korea 2000 / UTM-K (GRS80, 네이버·국토지리정보원)" },
  { epsg: 5187, label: "Korea 2000 / 동부원점 (GRS80)" },
  { epsg: 5185, label: "Korea 2000 / 서부원점 (GRS80)" },
  { epsg: 5188, label: "Korea 2000 / 동해(울릉)원점 (GRS80)" },
  { epsg: 5174, label: "Korean 1985 / 중부원점 (Bessel, 구 지적도)" },
  { epsg: 4326, label: "WGS 84 경위도" },
  { epsg: 4737, label: "Korea 2000 경위도" },
  { epsg: 3857, label: "Web Mercator (구글·카카오 지도)" },
  { epsg: 32652, label: "WGS 84 / UTM 52N" },
  { epsg: 32651, label: "WGS 84 / UTM 51N" },
];
