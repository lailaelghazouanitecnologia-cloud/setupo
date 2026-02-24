'use client';

import React from 'react';
import { LucideIcon, User, Settings, Power } from 'lucide-react';
import { useLayout } from '@/hooks/useLayout';
import { useAuth } from '@/hooks/useAuth';
import { getInitials } from '@/lib/auth/helpers';
import { cn } from '@/lib/utils';

interface DropdownItemProps 
{
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'destructive';
}

function DropdownItem({ icon: Icon, label, onClick, variant = 'default' }: DropdownItemProps) 
{
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'header-dropdown-item focus-ring',
        {
          'text-destructive hover:text-destructive': variant === 'destructive'
        }
      )}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </button>
  );
}

export function UserMenu() 
{
  const { dropdown } = useLayout();
  const { user, signOut } = useAuth();

  const isOpen = dropdown.open && dropdown.type === 'user';
  
  const handleToggle = () => {
    if (isOpen) {
      dropdown.close();
    } else {
      dropdown.openMenu('user');
    }
  };

  const handleItemClick = async (action: string) => {
    switch (action) {
      case 'profile':
        console.log('Navigate to profile');
        break;
      case 'settings':
        console.log('Navigate to settings');
        break;
      case 'logout':
        await signOut();
        break;
    }
    dropdown.close();
  };

  const initials = getInitials(user?.displayName || user?.email);

  return (
    <div className="relative" data-dropdown>
      <button
        type="button"
        onClick={handleToggle}
        className="header-avatar-reduced focus-ring"
        aria-label="User menu"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {initials}
      </button>
      
      <div className={cn(
        'header-dropdown',
        { 'show': isOpen }
      )}>
        <DropdownItem
          icon={User}
          label="Mi Perfil"
          onClick={() => handleItemClick('profile')}
        />
        <DropdownItem
          icon={Settings}
          label="Configuración"
          onClick={() => handleItemClick('settings')}
        />
        <DropdownItem
          icon={Power}
          label="Cerrar Sesión"
          onClick={() => handleItemClick('logout')}
          variant="destructive"
        />
      </div>
    </div>
  );
}
