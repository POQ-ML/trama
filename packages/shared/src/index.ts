export type HealthStatus = {
  status: string;
  service: string;
  environment: string;
  database?: string;
};
