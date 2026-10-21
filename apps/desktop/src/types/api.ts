export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  request_id: string;
}
