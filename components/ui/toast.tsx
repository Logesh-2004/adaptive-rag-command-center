"use client";

import * as React from "react";
import * as ToastPrimitives from "@radix-ui/react-toast";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastMessage = {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "destructive";
};

export function ToastProvider({
  children,
  messages,
  onDismiss,
}: {
  children: React.ReactNode;
  messages: ToastMessage[];
  onDismiss: (id: string) => void;
}) {
  return (
    <ToastPrimitives.Provider swipeDirection="right">
      {children}
      {messages.map((message) => (
        <ToastPrimitives.Root
          key={message.id}
          open
          onOpenChange={(open) => {
            if (!open) onDismiss(message.id);
          }}
          className={cn(
            "glass-panel grid w-[360px] gap-1 rounded-lg p-4 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-80 data-[state=open]:slide-in-from-right-full",
            message.variant === "destructive" && "border-destructive/40",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <ToastPrimitives.Title className="text-sm font-semibold">{message.title}</ToastPrimitives.Title>
              {message.description ? (
                <ToastPrimitives.Description className="mt-1 text-sm text-muted-foreground">
                  {message.description}
                </ToastPrimitives.Description>
              ) : null}
            </div>
            <ToastPrimitives.Close className="rounded-md p-1 text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <X className="h-4 w-4" />
            </ToastPrimitives.Close>
          </div>
        </ToastPrimitives.Root>
      ))}
      <ToastPrimitives.Viewport className="fixed right-4 top-4 z-50 flex max-h-screen w-[390px] flex-col gap-2 outline-none" />
    </ToastPrimitives.Provider>
  );
}
