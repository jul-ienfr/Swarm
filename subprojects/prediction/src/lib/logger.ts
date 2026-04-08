type LogMethod = (payload?: unknown, message?: string) => void

const noop: LogMethod = () => {}

export const logger = {
  error: noop,
  warn: noop,
  info: noop,
  debug: noop,
}
