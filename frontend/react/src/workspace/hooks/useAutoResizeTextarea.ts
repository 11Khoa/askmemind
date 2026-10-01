import { useLayoutEffect, useRef } from 'react'

export function useAutoResizeTextarea(
  value: string,
  minHeight = 38,
  maxHeight = 130,
) {
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return

    input.style.height = 'auto'
    const nextHeight = Math.min(input.scrollHeight, maxHeight)
    input.style.height = `${Math.max(nextHeight, minHeight)}px`
    input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [maxHeight, minHeight, value])

  return inputRef
}
