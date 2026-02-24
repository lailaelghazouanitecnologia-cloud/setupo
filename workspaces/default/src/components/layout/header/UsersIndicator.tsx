'use client';

import React from 'react';
import { Users } from 'lucide-react';
import { HeaderIcon } from './HeaderIcon';

interface UsersIndicatorProps 
{
  count: number;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}

export function UsersIndicator({ 
  count, 
  onClick,
  disabled = false, 
  className 
}: UsersIndicatorProps) 
{
  return (
    <HeaderIcon
      icon={Users}
      badge={count}
      onClick={onClick}
      disabled={disabled}
      className={className}
    />
  );
}