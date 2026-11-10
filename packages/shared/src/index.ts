export type HealthStatus = {
  status: string;
  service: string;
  environment: string;
  database?: string;
};

export type {
  UUID,
  ISODateTime,
  RunStatus,
  ErrorCode,
  DiscoveryCreate,
  ProjectRead,
  ArticleRead,
  TopicRead,
  EvidenceRead,
  SuggestionRead,
  RunRead,
  DiscoveryLimit,
  DiscoveryQuery,
  DiscoveryPage,
  FeedbackUpdate,
  FeedbackRead,
  MonitorUpdate,
  MonitorRead,
  ChangeRead,
  ChangePage,
  ApiErrorDetail,
  ApiError,
} from "./discovery";
