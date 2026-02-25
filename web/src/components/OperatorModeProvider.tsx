'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface OperatorModeContextValue {
  isOperator: boolean
}

const OperatorModeContext = createContext<OperatorModeContextValue>({ isOperator: false })

export function useOperatorMode() {
  return useContext(OperatorModeContext)
}

const COOKIE_NAME = 'rtp_operator'

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`
}

function deleteCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
}

export function OperatorModeProvider({ children }: { children: ReactNode }) {
  const [isOperator, setIsOperator] = useState(false)

  useEffect(() => {
    // Check URL params for operator activation/deactivation
    const params = new URLSearchParams(window.location.search)
    const opParam = params.get('op')

    if (opParam === 'off' || opParam === '0') {
      deleteCookie(COOKIE_NAME)
      setIsOperator(false)
      // Clean the URL
      params.delete('op')
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params}`
        : window.location.pathname
      window.history.replaceState({}, '', newUrl)
      return
    }

    if (opParam && opParam === process.env.NEXT_PUBLIC_RTP_OPERATOR_SECRET) {
      setCookie(COOKIE_NAME, 'active', 30)
      setIsOperator(true)
      // Clean the URL
      params.delete('op')
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params}`
        : window.location.pathname
      window.history.replaceState({}, '', newUrl)
      return
    }

    // No URL param — check existing cookie
    const cookie = getCookie(COOKIE_NAME)
    setIsOperator(cookie === 'active')
  }, [])

  return (
    <OperatorModeContext.Provider value={{ isOperator }}>
      {children}
    </OperatorModeContext.Provider>
  )
}
