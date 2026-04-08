import fs from 'node:fs'
import path from 'node:path'

export function resolvePredictionCliPath() {
  if (process.env.PREDICTION_CLI_PATH) {
    return process.env.PREDICTION_CLI_PATH
  }

  const candidates = [
    path.resolve(process.cwd(), 'scripts/mc-cli.cjs'),
    path.resolve(process.cwd(), 'subprojects/prediction/scripts/mc-cli.cjs'),
    path.resolve(process.cwd(), '../scripts/mc-cli.cjs'),
  ]

  return candidates.find((candidate) => fs.existsSync(candidate)) ?? candidates[0]
}
