import { createContext, useContext } from 'react';

export interface FeaturesContextValue {
  audioEnabled: boolean;
}

export const FeaturesContext = createContext<FeaturesContextValue>({ audioEnabled: true });

export function useFeatures(): FeaturesContextValue {
  return useContext(FeaturesContext);
}
