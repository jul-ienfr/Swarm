import geoMapDataCnProvinceRecords from '@/lib/prediction-markets/data/geomapdata-cn-provinces.json'

export type PredictionMarketGeoMapDataCnThinRecord = {
  adcode: string
  name: string
  level: 'country' | 'province'
  parent_adcode: string | null
  acroutes: string[]
  center: [number, number] | null
  centroid: [number, number] | null
  children_num: number
}

const GEO_MAP_DATA_CN_SOURCE_URL = 'https://github.com/lyhmyd1211/GeoMapData_CN'
const GEO_MAP_DATA_CN_THIN_RECORDS = geoMapDataCnProvinceRecords as PredictionMarketGeoMapDataCnThinRecord[]
const GEO_MAP_DATA_CN_BY_ADCODE = new Map(
  GEO_MAP_DATA_CN_THIN_RECORDS.map((record) => [record.adcode, record] as const),
)

function normalizeAdcode(value: string | number | null | undefined): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(Math.trunc(value))
  }
  const normalized = String(value ?? '').trim()
  return /^\d{6}$/.test(normalized) ? normalized : null
}

export function listGeoMapDataCnThinRecords(): PredictionMarketGeoMapDataCnThinRecord[] {
  return GEO_MAP_DATA_CN_THIN_RECORDS.map((record) => ({
    ...record,
    acroutes: [...record.acroutes],
    center: record.center ? [...record.center] as [number, number] : null,
    centroid: record.centroid ? [...record.centroid] as [number, number] : null,
  }))
}

export function getGeoMapDataCnSourceUrl(): string {
  return GEO_MAP_DATA_CN_SOURCE_URL
}

export function getGeoMapDataCnCoverageSummary() {
  const countryCount = GEO_MAP_DATA_CN_THIN_RECORDS.filter((record) => record.level === 'country').length
  const provinceCount = GEO_MAP_DATA_CN_THIN_RECORDS.filter((record) => record.level === 'province').length
  return {
    source_url: GEO_MAP_DATA_CN_SOURCE_URL,
    country_count: countryCount,
    province_count: provinceCount,
    total_records: GEO_MAP_DATA_CN_THIN_RECORDS.length,
    summary: `Thin GeoMapData_CN import with ${countryCount} country record and ${provinceCount} province-level records.`,
  }
}

export function findGeoMapDataCnRecordByAdcode(
  adcode: string | number | null | undefined,
): PredictionMarketGeoMapDataCnThinRecord | null {
  const normalized = normalizeAdcode(adcode)
  if (!normalized) return null
  return GEO_MAP_DATA_CN_BY_ADCODE.get(normalized) ?? null
}

export function findGeoMapDataCnRecords(
  adcodes: Array<string | number | null | undefined>,
): PredictionMarketGeoMapDataCnThinRecord[] {
  const out: PredictionMarketGeoMapDataCnThinRecord[] = []
  const seen = new Set<string>()

  for (const adcode of adcodes) {
    const record = findGeoMapDataCnRecordByAdcode(adcode)
    if (!record || seen.has(record.adcode)) continue
    seen.add(record.adcode)
    out.push(record)
  }

  return out
}
