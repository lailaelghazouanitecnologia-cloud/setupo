'use client';

import React, { useState } from 'react';
import { Coins, Plus, TrendingUp, Clock, Gift, ShoppingCart } from 'lucide-react';
import { useCredits } from '@/hooks/useCredits';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import type { CreditPackage, CreditTransaction } from '@/types/credits';

interface CreditsDisplayProps 
{
  className?: string;
  showLabel?: boolean;
  compact?: boolean;
}

export function CreditsDisplay({ 
  className, 
  showLabel = false,
  compact = true 
}: CreditsDisplayProps) 
{
  const { credits, loading, error, packages, addCredits, getTransactionHistory } = useCredits();
  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('buy');
  const [transactions, setTransactions] = useState<CreditTransaction[]>([]);

  const formatCredits = (amount: number): string => {
    if (amount >= 1000000) return `${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 1000) return `${(amount / 1000).toFixed(1)}K`;
    return amount.toString();
  };

  const handleOpenModal = async () => {
    setModalOpen(true);
    const history = await getTransactionHistory(10);
    setTransactions(history);
  };

  const handleBuyCredits = async (pkg: CreditPackage) => {
    // TODO: Integrar con sistema de pagos (Stripe/PayPal)
    console.log('Purchasing credits:', pkg);
    
    // Simular compra exitosa
    const totalCredits = pkg.credits + (pkg.bonus || 0);
    await addCredits(totalCredits, 'earned', `Compra de paquete ${pkg.name}`);
    
    setModalOpen(false);
  };

  if (loading) {
    return (
      <div className={cn('flex items-center gap-1', className)}>
        <Coins className="w-4 h-4 text-muted-foreground animate-pulse" />
        <span className="text-xs text-muted-foreground">...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn('flex items-center gap-1 text-destructive', className)}>
        <Coins className="w-4 h-4" />
        <span className="text-xs">Error</span>
      </div>
    );
  }

  const isLowCredits = credits < 100;

  return (
    <>
      <div 
        className={cn(
          'flex items-center gap-1 cursor-pointer transition-all duration-200',
          'hover:bg-header-hover rounded-md px-2 py-1',
          {
            'text-amber-600 dark:text-amber-400': isLowCredits,
            'text-foreground': !isLowCredits
          },
          className
        )}
        onClick={handleOpenModal}
        role="button"
        tabIndex={0}
        aria-label={`${credits} créditos disponibles`}
      >
        <Coins className={cn('w-4 h-4 flex-shrink-0', {
          'text-amber-600 dark:text-amber-400': isLowCredits,
          'text-primary': !isLowCredits
        })} />
        <span className={cn('text-xs font-medium', {
          'min-w-[30px] text-right': compact
        })}>
          {formatCredits(credits)}
        </span>
        {showLabel && (
          <span className="text-xs text-muted-foreground hidden sm:inline">
            créditos
          </span>
        )}
      </div>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Coins className="w-5 h-5 text-primary" />
              Gestión de Créditos
            </DialogTitle>
            <DialogDescription>
              Tienes {credits.toLocaleString()} créditos disponibles
            </DialogDescription>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="buy">
                <ShoppingCart className="w-4 h-4 mr-1" />
                Comprar
              </TabsTrigger>
              <TabsTrigger value="history">
                <Clock className="w-4 h-4 mr-1" />
                Historial
              </TabsTrigger>
              <TabsTrigger value="earn">
                <Gift className="w-4 h-4 mr-1" />
                Ganar Gratis
              </TabsTrigger>
            </TabsList>

            <TabsContent value="buy" className="space-y-4 mt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {packages.map((pkg) => (
                  <div
                    key={pkg.id}
                    className={cn(
                      'relative p-4 border rounded-xl cursor-pointer transition-all',
                      'hover:border-primary hover:shadow-lg',
                      {
                        'border-primary ring-2 ring-primary/20': pkg.popular,
                        'border-border': !pkg.popular
                      }
                    )}
                  >
                    {pkg.popular && (
                      <div className="absolute -top-2 left-4 bg-primary text-primary-foreground px-2 py-1 text-xs rounded-md font-medium">
                        Más Popular
                      </div>
                    )}
                    
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h3 className="font-semibold text-sm">{pkg.name}</h3>
                        <p className="text-lg font-bold text-primary">
                          ${pkg.price}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium">
                          {pkg.credits.toLocaleString()} créditos
                        </p>
                        {pkg.bonus && (
                          <p className="text-xs text-green-600 dark:text-green-400">
                            +{pkg.bonus.toLocaleString()} bonus
                          </p>
                        )}
                      </div>
                    </div>

                    <Button 
                      className="w-full"
                      onClick={() => handleBuyCredits(pkg)}
                      variant={pkg.popular ? 'default' : 'outline'}
                    >
                      Comprar {pkg.name}
                    </Button>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="history" className="space-y-4 mt-6">
              <div className="space-y-2">
                {transactions.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No hay transacciones recientes</p>
                  </div>
                ) : (
                  transactions.map((transaction) => (
                    <div
                      key={transaction.id}
                      className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          'w-8 h-8 rounded-full flex items-center justify-center',
                          {
                            'bg-green-100 dark:bg-green-900/20': transaction.amount > 0,
                            'bg-red-100 dark:bg-red-900/20': transaction.amount < 0
                          }
                        )}>
                          {transaction.amount > 0 ? (
                            <TrendingUp className="w-4 h-4 text-green-600 dark:text-green-400" />
                          ) : (
                            <Coins className="w-4 h-4 text-red-600 dark:text-red-400" />
                          )}
                        </div>
                        <div>
                          <p className="text-sm font-medium">{transaction.description}</p>
                          <p className="text-xs text-muted-foreground">
                            {new Date(transaction.createdAt).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <div className={cn(
                        'font-medium text-sm',
                        {
                          'text-green-600 dark:text-green-400': transaction.amount > 0,
                          'text-red-600 dark:text-red-400': transaction.amount < 0
                        }
                      )}>
                        {transaction.amount > 0 ? '+' : ''}{transaction.amount.toLocaleString()}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </TabsContent>

            <TabsContent value="earn" className="space-y-4 mt-6">
              <div className="grid gap-4">
                <div className="p-4 border rounded-xl bg-gradient-to-r from-primary/5 to-primary/10">
                  <div className="flex items-center gap-3 mb-2">
                    <Gift className="w-5 h-5 text-primary" />
                    <h3 className="font-semibold">Invita a tus amigos</h3>
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    Gana 500 créditos por cada amigo que se registre
                  </p>
                  <Button variant="outline" size="sm">
                    Compartir enlace de invitación
                  </Button>
                </div>

                <div className="p-4 border rounded-xl">
                  <div className="flex items-center gap-3 mb-2">
                    <TrendingUp className="w-5 h-5 text-green-600" />
                    <h3 className="font-semibold">Bonificación diaria</h3>
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    Obtén 25 créditos gratis cada día al iniciar sesión
                  </p>
                  <Button variant="outline" size="sm" disabled>
                    Ya reclamado hoy
                  </Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  );
}