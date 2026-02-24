'use client';

import React from 'react';
import { useLayout } from '@/hooks/useLayout';
import { cn } from '@/lib/utils';

interface ActivationStripProps 
{
  className?: string;
}

export function ActivationStrip({ className }: ActivationStripProps) 
{
  const { header, sidebar } = useLayout();

  const handleClick = () => {
    header.toggle();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <div 
      className={cn(
        'activation-strip',
        {
          'shifted': sidebar.visible
        },
        className
      )}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      aria-label={header.visible ? 'Ocultar header' : 'Mostrar header'}
      onKeyDown={handleKeyDown}
    />
  );
}