import { z } from 'zod'

import {
  predictionCryptoAssetUniverse,
  predictionCryptoExecutionProfiles,
  predictionCryptoMarketArchetypes,
  predictionCryptoVenues,
} from './universe'

export const predictionCryptoVenueSchema = z.enum(predictionCryptoVenues)
export const predictionCryptoAssetSchema = z.enum(predictionCryptoAssetUniverse)
export const predictionCryptoMarketArchetypeSchema = z.enum(predictionCryptoMarketArchetypes)
export const predictionCryptoExecutionProfileSchema = z.enum(predictionCryptoExecutionProfiles)

export const predictionCryptoScreenerSourceModeSchema = z.enum(['seeded', 'live', 'auto'])

export const predictionCryptoScreenerQuerySchema = z.object({
  venue: predictionCryptoVenueSchema.optional(),
  asset: predictionCryptoAssetSchema.optional(),
  archetype: predictionCryptoMarketArchetypeSchema.optional(),
  execution_profile: predictionCryptoExecutionProfileSchema.optional(),
  source_mode: predictionCryptoScreenerSourceModeSchema.default('auto'),
  limit: z.number().int().min(1).max(50).default(10),
})

export const predictionCryptoOpportunityIdSchema = z.string().min(1)
