export interface Investigator {
  name: string;
  role: string;
}

export interface Center {
  name: string;
  address: string;
  phone?: string;
}

export interface StudySynopsis {
  protocolTitle: string;
  protocolNumber: string;
  sponsor: string;
  clinicalCenter: string;
  bioanalyticalLab: string;
  clinicalPhase: string;

  investigationalProduct: string;
  activeSubstance: string;
  dosageForm: string;

  objectives: string;
  tasks: string[];

  design: string;
  methodology: string;
  population: string;
  inclusionCriteria: string[];
  exclusionCriteria: string[];
  withdrawalCriteria: string[];

  testProductRegimen: string;
  referenceProductRegimen: string;

  studyPeriods: string;
  duration: string;
  pkParameters: string;
  analyticalMethod: string;
  beCriteria: string;
  safetyAnalysis: string;
  sampleSizeCalculation: string;
  randomization: string;
  ethicalAspects: string;
  versionDate: string;

  markdown: string;
  yaml: string;

  bibliography: { title: string; uri: string }[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}
