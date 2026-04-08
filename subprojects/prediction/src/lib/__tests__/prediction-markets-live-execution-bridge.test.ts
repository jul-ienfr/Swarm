import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  spawnSync: vi.fn(),
  existsSync: vi.fn(),
}))

vi.mock('node:child_process', () => ({
  spawnSync: mocks.spawnSync,
}))

vi.mock('node:fs', () => ({
  existsSync: mocks.existsSync,
}))

describe('prediction markets live execution bridge', () => {
  const previousRepoRoot = process.env.PREDICTION_MARKETS_REPO_ROOT
  const previousPython = process.env.PREDICTION_MARKETS_PYTHON

  beforeEach(() => {
    vi.resetModules()
    mocks.spawnSync.mockReset()
    mocks.existsSync.mockReset()
    process.env.PREDICTION_MARKETS_REPO_ROOT = '/tmp/swarm-live-bridge'
    delete process.env.PREDICTION_MARKETS_PYTHON
    mocks.existsSync.mockImplementation((candidate: unknown) => {
      const normalized = String(candidate)
      return normalized === '/tmp/swarm-live-bridge/main.py'
        || normalized === '/tmp/swarm-live-bridge/.venv/bin/python'
    })
  })

  afterEach(() => {
    if (previousRepoRoot === undefined) delete process.env.PREDICTION_MARKETS_REPO_ROOT
    else process.env.PREDICTION_MARKETS_REPO_ROOT = previousRepoRoot

    if (previousPython === undefined) delete process.env.PREDICTION_MARKETS_PYTHON
    else process.env.PREDICTION_MARKETS_PYTHON = previousPython
  })

  it('invokes the Python bridge and returns the parsed payload', async () => {
    mocks.spawnSync.mockReturnValue({
      status: 0,
      stdout: JSON.stringify({
        ok: true,
        payload: {
          run_id: 'run-live-bridge-001',
          live_execution: {
            execution_id: 'live-exec-001',
            status: 'filled',
            dry_run: false,
          },
        },
      }),
      stderr: '',
    })

    const { executePredictionMarketLiveExecutionBridge } = await import('@/lib/prediction-markets/live-execution-bridge')
    const payload = executePredictionMarketLiveExecutionBridge({
      sourceRunId: 'run-source-001',
      executionRunId: 'run-source-001__live_abcd1234',
      marketId: 'pm_demo_market',
      stake: 25,
      actor: 'operator-a',
      approvedIntentId: 'intent-live-001',
      approvedBy: ['reviewer-a', 'reviewer-b'],
    })

    expect(mocks.spawnSync).toHaveBeenCalledTimes(1)
    expect(mocks.spawnSync.mock.calls[0]?.[0]).toBe('/tmp/swarm-live-bridge/.venv/bin/python')
    expect(mocks.spawnSync.mock.calls[0]?.[1]).toEqual([
      '-c',
      expect.stringContaining('PredictionMarketAdvisor'),
    ])
    expect(mocks.spawnSync.mock.calls[0]?.[2]).toMatchObject({
      cwd: '/tmp/swarm-live-bridge',
      encoding: 'utf-8',
    })
    expect(payload).toMatchObject({
      run_id: 'run-live-bridge-001',
      live_execution: {
        execution_id: 'live-exec-001',
        status: 'filled',
      },
    })
  })

  it('raises a prediction markets error when the Python bridge fails', async () => {
    mocks.spawnSync.mockReturnValue({
      status: 1,
      stdout: JSON.stringify({
        ok: false,
        error: 'bridge exploded',
      }),
      stderr: 'traceback',
    })

    const { executePredictionMarketLiveExecutionBridge } = await import('@/lib/prediction-markets/live-execution-bridge')

    expect(() =>
      executePredictionMarketLiveExecutionBridge({
        sourceRunId: 'run-source-002',
        executionRunId: 'run-source-002__live_abcd5678',
        marketId: 'pm_demo_market',
        stake: 10,
        actor: 'operator-b',
      }),
    ).toThrowError(/bridge exploded/)
  })
})
