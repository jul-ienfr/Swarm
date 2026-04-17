import { describe, expect, it } from 'vitest'
import {
  predictionMarketContractDocs,
  predictionMarketContractExampleNames,
  predictionMarketContractExamples,
  type PredictionMarketContractExampleName,
} from '@/lib/prediction-markets/contract-examples'
import {
  autonomousAgentReportSchema,
  approvalTradeTicketSchema,
  basketIntentPreviewSchema,
  capitalLedgerSnapshotSchema,
  crossVenueMarketRefSchema,
  crossVenueMatchSchema,
  decisionPacketSchema,
  evidencePacketSchema,
  executionIntentPreviewSchema,
  forecastPacketSchema,
  latencyReferenceBundleSchema,
  marketDescriptorSchema,
  marketRegimeSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  predictionMarketArtifactRefSchema,
  predictionMarketPacketBundleSchema,
  predictionMarketBudgetsSchema,
  predictionMarketResearchPipelineSummarySchema,
  predictionMarketResearchPipelineTraceSchema,
  predictionMarketRunSummarySchema,
  predictionMarketsAdviceRequestSchema,
  predictionMarketsReplayRequestSchema,
  quotePairIntentPreviewSchema,
  resolutionAnomalyReportSchema,
  resolutionPolicySchema,
  runManifestSchema,
  strategyCandidatePacketSchema,
  strategyDecisionPacketSchema,
  strategyShadowReportSchema,
  strategyShadowSummarySchema,
  tradeIntentSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

const contractSchemas: Record<
  PredictionMarketContractExampleName,
  { parse: (value: unknown) => unknown }
> = {
  decisionPacket: decisionPacketSchema,
  marketRegime: marketRegimeSchema,
  executionIntentPreview: executionIntentPreviewSchema,
  quotePairIntentPreview: quotePairIntentPreviewSchema,
  basketIntentPreview: basketIntentPreviewSchema,
  latencyReferenceBundle: latencyReferenceBundleSchema,
  resolutionAnomalyReport: resolutionAnomalyReportSchema,
  autonomousAgentReport: autonomousAgentReportSchema,
  strategyShadowSummary: strategyShadowSummarySchema,
  strategyShadowReport: strategyShadowReportSchema,
  strategyCandidatePacket: strategyCandidatePacketSchema,
  strategyDecisionPacket: strategyDecisionPacketSchema,
  predictionMarketPacketBundle: predictionMarketPacketBundleSchema,
  predictionMarketBudgets: predictionMarketBudgetsSchema,
  marketDescriptor: marketDescriptorSchema,
  resolutionPolicy: resolutionPolicySchema,
  marketSnapshot: marketSnapshotSchema,
  evidencePacket: evidencePacketSchema,
  crossVenueMarketRef: crossVenueMarketRefSchema,
  crossVenueMatch: crossVenueMatchSchema,
  venueCapabilities: venueCapabilitiesSchema,
  venueHealthSnapshot: venueHealthSnapshotSchema,
  capitalLedgerSnapshot: capitalLedgerSnapshotSchema,
  tradeIntent: tradeIntentSchema,
  approvalTradeTicket: approvalTradeTicketSchema,
  forecastPacket: forecastPacketSchema,
  marketRecommendationPacket: marketRecommendationPacketSchema,
  predictionMarketArtifactRef: predictionMarketArtifactRefSchema,
  runManifest: runManifestSchema,
  predictionMarketRunSummary: predictionMarketRunSummarySchema,
  predictionMarketsAdviceRequest: predictionMarketsAdviceRequestSchema,
  predictionMarketsReplayRequest: predictionMarketsReplayRequestSchema,
  predictionMarketResearchPipelineTrace: predictionMarketResearchPipelineTraceSchema,
  predictionMarketResearchPipelineSummary: predictionMarketResearchPipelineSummarySchema,
}

describe('prediction market contract examples', () => {
  it('keeps every canonical example parseable against the current schemas', () => {
    for (const name of predictionMarketContractExampleNames) {
      expect(() => contractSchemas[name].parse(predictionMarketContractExamples[name])).not.toThrow()
    }
  })

  it('accepts the product-facing predict and predict-deep request contract aliases', () => {
    const shallow = predictionMarketsAdviceRequestSchema.parse({
      venue: 'polymarket',
      market_id: 'alias-contract-market',
      request_mode: 'predict',
      response_variant: 'standard',
    })
    const deep = predictionMarketsAdviceRequestSchema.parse({
      venue: 'polymarket',
      market_id: 'alias-contract-market',
      request_mode: 'predict-deep',
      response_variant: 'research-heavy',
      variant_tags: ['polfish', 'mirofish-pm'],
    })

    expect(shallow.request_mode).toBe('predict')
    expect(shallow.response_variant).toBe('standard')
    expect(deep.request_mode).toBe('predict_deep')
    expect(deep.response_variant).toBe('research_heavy')
    expect(deep.variant_tags).toEqual(['polfish', 'mirofish-pm'])
  })

  it('documents required fields that are present in the canonical examples', () => {
    for (const name of predictionMarketContractExampleNames) {
      const doc = predictionMarketContractDocs[name]
      const example = predictionMarketContractExamples[name] as Record<string, unknown>

      expect(doc.schema.length).toBeGreaterThan(0)
      expect(doc.purpose.length).toBeGreaterThan(0)
      expect(doc.required_fields.length).toBeGreaterThan(0)

      for (const field of doc.required_fields) {
        expect(field.field.length).toBeGreaterThan(0)
        expect(field.type.length).toBeGreaterThan(0)
        expect(field.description.length).toBeGreaterThan(0)
        expect(example[field.field]).not.toBeUndefined()
      }
    }
  })

  it('keeps the examples aligned as a coherent end-to-end contract chain', () => {
    expect(predictionMarketContractExamples.marketSnapshot.market.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.resolutionPolicy.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.crossVenueMarketRef.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.crossVenueMatch.left_market_ref.market_id).toBe(
      predictionMarketContractExamples.crossVenueMarketRef.market_id,
    )
    expect(predictionMarketContractExamples.forecastPacket.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.marketRecommendationPacket.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.tradeIntent.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.approvalTradeTicket.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.approvalTradeTicket.approval_state.status).toBe('approved')
    expect(predictionMarketContractExamples.predictionMarketsAdviceRequest.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.predictionMarketsAdviceRequest.request_mode).toBe('predict_deep')
    expect(predictionMarketContractExamples.predictionMarketsAdviceRequest.response_variant).toBe('research_heavy')
    expect(predictionMarketContractExamples.predictionMarketRunSummary.manifest.run_id).toBe(
      predictionMarketContractExamples.runManifest.run_id,
    )
    expect(predictionMarketContractExamples.runManifest.artifact_refs[1]).toEqual(
      predictionMarketContractExamples.predictionMarketArtifactRef,
    )
    expect(predictionMarketContractExamples.predictionMarketsReplayRequest.run_id).toBe(
      predictionMarketContractExamples.runManifest.run_id,
    )
    expect(predictionMarketContractExamples.predictionMarketResearchPipelineTrace.market_id).toBe(
      predictionMarketContractExamples.marketDescriptor.market_id,
    )
    expect(predictionMarketContractExamples.predictionMarketResearchPipelineSummary.trace_id).toBe(
      predictionMarketContractExamples.predictionMarketResearchPipelineTrace.trace_id,
    )
  })

  it('declares swarm as the runtime used by the canonical decision contract example', () => {
    expect(predictionMarketContractExamples.decisionPacket.runtime_used).toBe('swarm')
  })

  it('keeps canonical advisor packet contract metadata attached to the examples', () => {
    expect(predictionMarketContractExamples.decisionPacket.packet_kind).toBe('decision')
    expect(predictionMarketContractExamples.decisionPacket.contract_id).toBe('1.0.0:decision:1.0.0:market_only')
    expect(predictionMarketContractExamples.forecastPacket.packet_kind).toBe('forecast')
    expect(predictionMarketContractExamples.forecastPacket.contract_id).toBe('1.0.0:forecast:1.0.0:market_only')
    expect(predictionMarketContractExamples.marketRecommendationPacket.packet_kind).toBe('recommendation')
    expect(predictionMarketContractExamples.marketRecommendationPacket.contract_id).toBe('1.0.0:recommendation:1.0.0:market_only')
  })
})
