export type MeteoTemperatureUnit = 'c' | 'f'
export type MeteoTemperatureKind = 'high' | 'low'
export type MeteoForecastProviderKind = 'open-meteo' | 'nws' | 'meteostat' | 'official-observation' | 'custom'
export type MeteoResolutionProvider = 'noaa' | 'wunderground' | 'nws' | 'hong-kong-observatory' | 'unknown'
export type MeteoResolutionStationType = 'airport' | 'weather-station' | 'unknown'
export type MeteoResolutionPrecision = 'whole-degree' | 'tenth-degree' | 'unknown'

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

export type MeteoExecutionCandidate = {
  label: string
  side: 'yes' | 'no'
  marketPrice: number
  fairPrice: number
  edge: number
  edgeBps: number
  expectedValue: number
  expectedRoi: number | null
  confidence: 'low' | 'medium' | 'high'
  priority: 'low' | 'medium' | 'high'
  tradeable: boolean
  maxEntryPrice: number
  noTradeAbove: number
  reasonCodes: string[]
}

export type MeteoMarketAnomaly = {
  type: 'adjacent_gap'
  label: string
  severity: 'low' | 'medium' | 'high'
  details: string
}

export type MeteoExecutionSummary = {
  candidateCount: number
  tradeableCount: number
  highPriorityCount: number
  anomalyCount: number
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

export type MeteoResolutionSource = {
  provider: MeteoResolutionProvider
  sourceUrl: string | null
  stationName: string | null
  stationCode: string | null
  stationType: MeteoResolutionStationType
  measurementField: string | null
  measurementKind: MeteoTemperatureKind | 'unknown'
  unit: MeteoTemperatureUnit | null
  precision: MeteoResolutionPrecision
  finalizationRule: string | null
  revisionRule: string | null
  extractedFrom: Array<'resolutionSource' | 'description' | 'question' | 'rules'>
  confidence: number
}

export type MeteoStationMetadata = {
  stationName: string | null
  stationCode: string | null
  stationType: MeteoResolutionStationType
  countryOrRegion: string | null
  city: string | null
  sourceProvider: MeteoResolutionProvider
  sourceUrl: string | null
  sourceNetwork: string | null
  notes: string[]
}

export type MeteoResolutionAnalysis = {
  isOfficialSourceIdentified: boolean
  needsManualReview: boolean
  confidence: number
}

export type MeteoResolutionSourceRoute = {
  provider: MeteoResolutionProvider
  station_code: string | null
  primary_poll_url: string | null
  fallback_poll_urls: string[]
  measurement_path: string | null
  expected_lag_seconds: number | null
  freshness_sla_seconds: number | null
  official_lag_seconds: number | null
}

export type MeteoResolutionSourceObservation = {
  provider: MeteoResolutionProvider
  station_code: string | null
  observed_at: string | null
  temperature: number
  unit: MeteoTemperatureUnit
  source_url: string
  age_seconds: number | null
  is_fresh: boolean | null
}

export type MeteoPolymarketEventQuoteInput = {
  event_id?: string | null
  ts?: string | null
  venue?: 'polymarket' | null
  market_id?: string | null
  event_type?: 'quote' | null
  best_bid?: number | null
  best_ask?: number | null
  last_trade_price?: number | null
  bid_size?: number | null
  ask_size?: number | null
  quote_age_ms?: number | null
}

export type MeteoPolymarketEventInput = {
  title?: string | null
  description?: string | null
  rules?: string | null
  resolution_source?: string | null
  market_id?: string | null
  quote_event?: MeteoPolymarketEventQuoteInput | null
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
