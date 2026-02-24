'use client';

import React, { useEffect } from 'react';
import { useDeviceStore } from '@/stores/device-store';
import { useLayoutStore } from '@/stores/layout-store';

interface LayoutProviderProps
{
  children: React.ReactNode;
}

export function LayoutProvider({ children }: LayoutProviderProps)
{
  const { setViewport, setOnlineStatus } = useDeviceStore();

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleResize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      setViewport(width, height);
    };

    const handleOnline = () => setOnlineStatus(true);
    const handleOffline = () => setOnlineStatus(false);

    window.addEventListener('resize', handleResize);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [setViewport, setOnlineStatus]);

  return <>{children}</>;
}
