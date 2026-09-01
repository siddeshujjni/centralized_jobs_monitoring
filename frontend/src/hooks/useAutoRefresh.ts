import { useState, useEffect, useCallback, useRef } from 'react';

export function useAutoRefresh(callback: () => void, intervalMs: number = 30000) {
  const [countdown, setCountdown] = useState(Math.floor(intervalMs / 1000));
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await callbackRef.current();
    } finally {
      setIsRefreshing(false);
      setLastRefresh(new Date());
      setCountdown(Math.floor(intervalMs / 1000));
    }
  }, [intervalMs]);

  // Countdown timer
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          refresh();
          return Math.floor(intervalMs / 1000);
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [intervalMs, refresh]);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  return { countdown, lastRefresh, isRefreshing, refresh };
}
