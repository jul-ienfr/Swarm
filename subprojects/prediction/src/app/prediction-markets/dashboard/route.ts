import { buildPredictionMarketsDashboardHtml } from '@/lib/prediction-markets/dashboard'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET(_request: Request) {
  return new Response(
    buildPredictionMarketsDashboardHtml({
      apiBasePath: '/api/v1/prediction-markets',
      title: 'Prediction Markets Dashboard',
      mode: 'embedded-app-route',
    }),
    {
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'cache-control': 'no-store',
      },
    },
  )
}
