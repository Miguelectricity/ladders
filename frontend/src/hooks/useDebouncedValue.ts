import { useEffect, useState } from 'react'

/**
 * Trails `value` by `delay` ms, so typing doesn't fire a request per keystroke.
 *
 * The cleanup cancelling the pending timer is the whole debounce mechanism, not
 * an afterthought: each new value throws away the update the previous one had
 * scheduled, so only a pause in typing lets one through.
 */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
