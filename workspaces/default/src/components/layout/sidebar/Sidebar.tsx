'use client';

import React, { useState } from 'react';
import { X, Plus, Gift, Users, Copy, Check, Share2, ChevronUp } from 'lucide-react';
import { useLayout } from '@/hooks/useLayout';
import { Navigation } from './Navigation';
import { cn } from '@/lib/utils';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface SidebarProps 
{
  className?: string;
}

export function Sidebar({ className }: SidebarProps) 
{
  const { sidebar } = useLayout();

  return (
    <aside 
      className={cn(
        'sidebar-base',
        {
          'sidebar-visible': sidebar.visible
        },
        className
      )}
    >
      <SidebarHeader />
      <SidebarContent />
    </aside>
  );
}

function SidebarHeader() 
{
  const { sidebar } = useLayout();

  return (
    <div className="sidebar-header">
      <span className="sidebar-title">Sonzar</span>
      <button
        type="button"
        onClick={sidebar.toggle}
        className="sidebar-close focus-ring"
        aria-label="Cerrar sidebar"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

function SidebarContent() 
{
  return (
    <div className="sidebar-content">
      <button className="task-btn">
        <Plus className="w-4 h-4" />
        Nueva conversación
      </button>
      
      <Navigation />
      
      <div className="chat-section">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-3">
          Conversaciones Recientes
        </h3>
        <div className="chat-scroll-container">
          <ChatList />
        </div>
      </div>
      
      <div className="invite-section-bottom">
        <InviteFriend />
      </div>
    </div>
  );
}

function InviteFriend()
{
  const { user } = useAuth();
  const [copied, setCopied] = useState(false);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);

  if (!user) return null;

  const referralCode = `VAOLER${user.id?.slice(-6).toUpperCase() || 'DEMO'}`;
  const referralLink = `https://vaoler.com/register?ref=${referralCode}`;

  const handleCopyReferralLink = () => {
    navigator.clipboard.writeText(referralLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: 'Únete a Vaoler',
        text: 'Únete a Vaoler y obtén 500 créditos gratis usando mi código de invitación',
        url: referralLink,
      });
    } else {
      handleCopyReferralLink();
    }
  };

  return (
    <>
      <div 
        className="invite-compact"
        onClick={() => setInviteModalOpen(true)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gift className="w-4 h-4 text-primary flex-shrink-0" />
            <div>
              <span className="invite-text block">Invita amigos</span>
              <span className="text-xs text-muted-foreground">500 créditos cada uno</span>
            </div>
          </div>
          <ChevronUp className="w-3 h-3 text-muted-foreground rotate-90" />
        </div>
      </div>

      <Dialog open={inviteModalOpen} onOpenChange={setInviteModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Gift className="w-5 h-5 text-primary" />
              Comparte Vaoler con un amigo
            </DialogTitle>
            <DialogDescription>
              Obtén 500 créditos cada uno
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="text-center py-6">
              <div className="w-16 h-16 bg-gradient-to-br from-primary/20 to-accent/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <Users className="w-8 h-8 text-primary" />
              </div>
              <p className="text-sm text-muted-foreground mb-4">
                Cuando tu amigo se registre usando tu enlace, ambos recibiréis 500 créditos automáticamente.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-foreground block mb-2">
                  Tu código de invitación
                </label>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-muted rounded border px-3 py-2">
                    <span className="text-sm font-mono">{referralCode}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCopyReferralLink}
                    className="px-3"
                  >
                    {copied ? (
                      <Check className="w-4 h-4 text-green-600" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-foreground block mb-2">
                  Enlace de invitación
                </label>
                <div className="bg-muted rounded border px-3 py-2">
                  <span className="text-xs text-muted-foreground break-all">
                    {referralLink}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <Button 
                className="flex-1"
                onClick={handleShare}
              >
                <Share2 className="w-4 h-4 mr-2" />
                Compartir
              </Button>
              <Button 
                variant="outline"
                onClick={handleCopyReferralLink}
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4 mr-2 text-green-600" />
                    Copiado
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4 mr-2" />
                    Copiar
                  </>
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ChatList() 
{
  // Simular 50 conversaciones para mostrar el scroll
  const chats = [
    { id: '1', name: 'Proyecto React', time: '2 min', active: true },
    { id: '2', name: 'Consulta TypeScript', time: '1 hora' },
    { id: '3', name: 'Diseño de API', time: '3 horas' },
    { id: '4', name: 'Optimización DB', time: '1 día' },
    { id: '5', name: 'Next.js App Router', time: '2 días' },
    { id: '6', name: 'Tailwind CSS', time: '3 días' },
    { id: '7', name: 'Zustand Store', time: '4 días' },
    { id: '8', name: 'Supabase Auth', time: '5 días' },
    { id: '9', name: 'Component Library', time: '1 sem' },
    { id: '10', name: 'Testing Setup', time: '1 sem' },
    { id: '11', name: 'CI/CD Pipeline', time: '2 sem' },
    { id: '12', name: 'Docker Config', time: '2 sem' },
    { id: '13', name: 'AWS Deploy', time: '3 sem' },
    { id: '14', name: 'Performance Opt', time: '3 sem' },
    { id: '15', name: 'SEO Implementation', time: '1 mes' },
    { id: '16', name: 'Analytics Setup', time: '1 mes' },
    { id: '17', name: 'Error Handling', time: '1 mes' },
    { id: '18', name: 'Logging System', time: '1 mes' },
    { id: '19', name: 'Security Audit', time: '2 mes' },
    { id: '20', name: 'Code Review', time: '2 mes' },
  ];

  return (
    <ul className="space-y-1">
      {chats.map((chat) => (
        <li
          key={chat.id}
          className={cn(
            'chat-item',
            {
              'active': chat.active
            }
          )}
        >
          <div className="flex items-center justify-between">
            <span className="chat-name">{chat.name}</span>
            <span className="chat-time">{chat.time}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}