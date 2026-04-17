import { NextResponse } from 'next/server'

const endpoints = [
  {
    path: '/prediction-markets/dashboard',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/overview',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/runs',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/runs/:run_id',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/benchmark',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/arbitrage',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/arbitrage/:candidate_id',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/venues/:venue',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/events',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/live-intents',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/live-intents',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id/approve',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id/reject',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/prediction-markets/advise',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/prediction-markets/predict',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/prediction-markets/predict-deep',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/prediction-markets/replay',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/predict',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/predict-deep',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/runs/:run_id/live',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/runs/:run_id/dispatch',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/runs/:run_id/paper',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/runs/:run_id/shadow',
    auth: 'operator',
    method: 'POST',
  },
  {
    path: '/api/v1/prediction-markets/runs/:run_id',
    auth: 'viewer',
    method: 'GET',
  },
  {
    path: '/api/prediction-markets/runs',
    auth: 'viewer',
    method: 'GET',
  },
]

export async function GET() {
  return NextResponse.json({ endpoints })
}
