export type MeteoTemperatureUnit = 'c' | 'f'
export type MeteoTemperatureKind = 'high' | 'low'
export type MeteoForecastProviderKind = 'open-meteo' | 'nws' | 'meteostat' | 'official-observation' | 'custom'

export type MeteoRangeBound = {
  value: number
  inclusive: boolean
}

export type MeteoTemperatureBin = {
  label: string
  unit: MeteoTemperatureUnit
  lower: MeteoRangeBound | null
  upper: MeteoRangeBound | null
}

export type MeteoMarketSpec = {
  question: string
  city: string | null
  countryOrRegion: string | null
  marketDate: string | null
  kind: MeteoTemperatureKind | null
  unit: MeteoTemperatureUnit | null
  bins: MeteoTemperatureBin[]
}

export type MeteoForecastPoint = {
  provider: string
  mean: number
  stddev: number
  weight?: number
}

export type MeteoForecastSource = {
  provider: string
  providerKind: MeteoForecastProviderKind
  sourceLabel: string
  weight: number
}

export type MeteoForecastContribution = MeteoForecastSource & {
  mean: number
  stddev: number
}

export type MeteoForecastConsensus = {
  mean: number
  stddev: number
  totalWeight: number
  providers: string[]
  contributions: MeteoForecastContribution[]
}

export type MeteoPricingInput = {
  spec: MeteoMarketSpec
  forecastPoints: MeteoForecastPoint[]
  marketPrices?: Record<string, number>
}

export type MeteoFetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>

export type MeteoProviderFetchOptions = {
  fetchImpl?: MeteoFetchLike
  cacheTtlMs?: number
  retryCount?: number
}

export type MeteoOpenMeteoFetchParams = {
  latitude: number
  longitude: number
  kind: MeteoTemperatureKind
  weight?: number
  model?: string
} & MeteoProviderFetchOptions

export type MeteoNwsFetchParams = {
  latitude: number
  longitude: number
  kind: MeteoTemperatureKind
  weight?: number
  userAgent?: string
} & MeteoProviderFetchOptions

export type MeteoMeteostatFetchParams = {
  latitude: number
  longitude: number
  kind: MeteoTemperatureKind
  start: string
  end: string
  weight?: number
  altitude?: number
  units?: 'metric' | 'imperial' | 'scientific'
  apiKey?: string
  sourceLabel?: string
} & MeteoProviderFetchOptions

export type MeteoBinFairValue = {
  label: string
  probability: number
  fairYesPrice: number
  fairNoPrice: number
  marketYesPrice: number | null
  marketNoPrice: number | null
  edge: number | null
  yesEdge: number | null
  noEdge: number | null
  expectedValueYes: number | null
  expectedValueNo: number | null
  expectedRoiYes: number | null
  expectedRoiNo: number | null
  recommendedSide: 'yes' | 'no' | 'pass'
}

export type MeteoPricingOpportunity = {
  label: string
  side: 'yes' | 'no'
  edge: number
  expectedValue: number
  expectedRoi: number | null
  fairPrice: number
  marketPrice: number
}

export type MeteoBestBetsSummary = {
  summary: string
  actionableCount: number
  strongestOpportunity: MeteoPricingOpportunity | null
  topOpportunities: MeteoPricingOpportunity[]
  recommendedSideCounts: {
    yes: number
    no: number
    pass: number
  }
  noTradeLabels: string[]
}

export type MeteoPricingReport = {
  mean: number
  stddev: number
  unit: MeteoTemperatureUnit
  bins: MeteoBinFairValue[]
  opportunities: MeteoPricingOpportunity[]
  marketSnapshot: {
    pricedBinCount: number
    yesPriceSum: number | null
    overround: number | null
  }
  provenance: {
    providerCount: number
    providers: string[]
    contributions: MeteoForecastContribution[]
  }
}

export type MeteoOpenMeteoTemperaturePayload = {
  provider?: string
  model?: string
  daily: {
    temperature_2m_max?: number[]
    temperature_2m_min?: number[]
  }
  daily_units?: {
    temperature_2m_max?: string
    temperature_2m_min?: string
  }
}

export type MeteoNwsTemperaturePayload = {
  provider?: string
  periods: Array<{
    isDaytime?: boolean
    temperature: number
    temperatureUnit: 'F' | 'C'
    name?: string
  }>
}

export type MeteoNwsPointMetadata = {
  forecast?: string
  forecastHourly?: string
  gridId?: string
  gridX?: number
  gridY?: number
}

export type MeteoMeteostatDailyPayload = {
  provider?: string
  data: Array<{
    date: string
    tavg?: number | null
    tmin?: number | null
    tmax?: number | null
  }>
  meta?: {
    units?: string
  }
}
