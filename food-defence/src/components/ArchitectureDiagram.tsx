import React from 'react';
import { ArrowDown, ArrowUp, Database, Box, Cpu, Shield, User, Users, BookOpen, BarChart3, GitMerge, FileText, PieChart, Lock, Key } from 'lucide-react';

// Define TypeScript interface
interface DiagramBoxProps {
  title: string;
  description: string;
  color: string;
  icon: React.ReactNode;
  techStack?: string;
}

const ArchitectureDiagram = () => {
  // Define colors for different component types
  const colors = {
    database: "#DDF1D4",
    api: "#D4E8F1",
    service: "#F1ECD4",
    security: "#F1D4D4",
    ui: "#D4D4F1",
    integration: "#E9D4F1",
    client: "#F1D4E3",
    border: "#1A73E8",
    arrow: "#5f6368",
    heading: "#1A73E8",
  };

  // Define styles for components
  const styles = {
    container: 'w-full min-h-screen bg-white p-6 font-sans',
    heading: `text-2xl font-bold mb-2 text-[${colors.heading}]`,
    subHeading: 'text-xl font-semibold mb-4 text-gray-700',
    description: 'text-sm text-gray-600 mb-6 max-w-4xl',
    legend: 'grid grid-cols-3 gap-4 mb-6 text-sm',
    legendItem: 'flex items-center gap-2',
    diagramContainer: 'w-full overflow-auto',
    layer: 'flex justify-center items-start gap-6 mb-8 relative',
    sectionTitle: 'font-semibold text-gray-700 mb-5 text-center',
    layerHeading: 'text-base font-semibold text-gray-700 absolute left-0 top-1/2 transform -translate-y-1/2',
    box: 'rounded-lg px-4 py-3 flex flex-col justify-center items-center text-center shadow-sm border border-blue-400 w-52 h-36 relative',
    boxTitle: 'font-bold text-sm mb-1',
    boxDescription: 'text-xs text-gray-600',
    iconBox: 'absolute -top-4 bg-white rounded-full p-2 border border-blue-400',
    arrow: 'text-gray-400',
    dataFlow: 'text-xs text-gray-500 absolute',
    databaseLabel: 'text-xs text-blue-700 font-medium text-center absolute -top-8 w-full',
    techStack: 'text-xs italic text-blue-600 mt-2'
  };

  // Helper to create a layered diagram box
  const DiagramBox: React.FC<DiagramBoxProps> = ({ title, description, color, icon, techStack }) => (
    <div className={styles.box} style={{ backgroundColor: color, borderColor: "#3B82F6" }}>
      <div className={styles.iconBox} style={{ borderColor: "#3B82F6" }}>
        {icon}
      </div>
      <div className={styles.boxTitle}>{title}</div>
      <div className={styles.boxDescription}>{description}</div>
      {techStack && <div className={styles.techStack}>{techStack}</div>}
    </div>
  );

  // Create a bidirectional connection line for better visual flow
  const BiDirectionalConnection = () => (
    <div className="relative flex justify-center my-6 h-28">
      <div className="relative h-full w-0.5 bg-gray-400">
        {/* Arrows directly on the line */}
        <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2">
          <ArrowDown size={16} className="text-gray-500" />
        </div>
        
        <div className="absolute -top-1 left-1/2 transform -translate-x-1/2">
          <ArrowUp size={16} className="text-gray-500" />
        </div>
      </div>
      
      {/* Flow label */}
      <div className="absolute top-1/2 transform -translate-y-1/2 left-1/2 ml-8 text-xs text-gray-500">
        Data flow
      </div>
    </div>
  );

  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>DEFENSEFOOD Task 5.4: Food Threat Capability & Training Tool</h1>
      <h2 className={styles.subHeading}>Architectural Design with Tech Stack & Data Flow</h2>
      <p className={styles.description}>
        This architecture diagram illustrates the backend system design for Task 5.4, showcasing the tech stack and data flow for the adaptive learning tool that assesses food threat management capabilities and delivers personalized training.
      </p>
      
      {/* Legend */}
      <div className={styles.legend}>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.database }}></div>
          <span>Data Storage</span>
        </div>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.api }}></div>
          <span>API & Gateway Services</span>
        </div>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.service }}></div>
          <span>Core Services</span>
        </div>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.security }}></div>
          <span>Security Components</span>
        </div>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.integration }}></div>
          <span>Integration Layers</span>
        </div>
        <div className={styles.legendItem}>
          <div className="w-4 h-4 rounded" style={{ backgroundColor: colors.client }}></div>
          <span>Client/UI Layer</span>
        </div>
      </div>
      
      <div className={styles.diagramContainer}>
        {/* Client Layer */}
        <div className={styles.layer}>
          <div className="w-full text-center relative">
            <h3 className={styles.sectionTitle}>Client Layer</h3>
            <div className="flex justify-center">
              <DiagramBox 
                title="Web Application" 
                description="Responsive interface for user interaction & training delivery"
                color={colors.client}
                icon={<User size={18} />}
                techStack="React, Redux, TailwindCSS"
              />
            </div>
          </div>
        </div>
        
        <BiDirectionalConnection />
        
        {/* API Gateway Layer */}
        <div className={styles.layer}>
          <div className="w-full text-center relative">
            <h3 className={styles.sectionTitle}>API Gateway</h3>
            <div className="flex justify-center">
              <DiagramBox 
                title="API Gateway Service" 
                description="Unified entry point for all client requests, security filtering"
                color={colors.api}
                icon={<GitMerge size={18} />}
                techStack="Node.js, Express, API Gateway"
              />
            </div>
          </div>
        </div>
        
        <BiDirectionalConnection />
        
        {/* Core Services Layer */}
        <div className={styles.layer}>
          <h3 className={styles.sectionTitle}>Core Services</h3>
          <div className="flex flex-wrap justify-center gap-8">
            <DiagramBox 
              title="User Management" 
              description="Profile handling, authentication, authorization"
              color={colors.service}
              icon={<Users size={18} />}
              techStack="Node.js, Express"
            />
            
            <DiagramBox 
              title="Competency Assessment" 
              description="User capability evaluation, gap analysis"
              color={colors.service}
              icon={<BarChart3 size={18} />}
              techStack="Python, FastAPI"
            />
            
            <DiagramBox 
              title="Learning Path Engine" 
              description="Adaptive learning algorithms, recommendations"
              color={colors.service}
              icon={<GitMerge size={18} />}
              techStack="Python, scikit-learn, TensorFlow"
            />
            
            <DiagramBox 
              title="Content Management" 
              description="Training materials handling, metadata management"
              color={colors.service}
              icon={<BookOpen size={18} />}
              techStack="Node.js, Content API"
            />
          </div>
        </div>
        
        <BiDirectionalConnection />
        
        {/* Integration Layer */}
        <div className={styles.layer}>
          <h3 className={styles.sectionTitle}>Integration & AI Layer</h3>
          <div className="flex flex-wrap justify-center gap-8">
            <DiagramBox 
              title="LLM Service" 
              description="AI-powered content generation & recommendations"
              color={colors.integration}
              icon={<Cpu size={18} />}
              techStack="Python, LangChain, OpenAI API"
            />
            
            <DiagramBox 
              title="External Training API" 
              description="Integration with third-party training platforms"
              color={colors.integration}
              icon={<Box size={18} />}
              techStack="Node.js, GraphQL, REST Adapters"
            />
            
            <DiagramBox 
              title="Knowledge Platform Link" 
              description="Connection to main DEFENSEFOOD platform (Task 5.1)"
              color={colors.integration}
              icon={<GitMerge size={18} />}
              techStack="Node.js, REST API, WebSockets"
            />
            
            <DiagramBox 
              title="Analytics Engine" 
              description="Performance tracking, engagement metrics"
              color={colors.integration}
              icon={<PieChart size={18} />}
              techStack="Python, Pandas, Apache Spark"
            />
          </div>
        </div>
        
        <BiDirectionalConnection />
        
        {/* Security Layer */}
        <div className={styles.layer}>
          <h3 className={styles.sectionTitle}>Security Layer</h3>
          <div className="flex flex-wrap justify-center gap-8">
            <DiagramBox 
              title="Authentication Service" 
              description="User authentication, SSO, identity verification"
              color={colors.security}
              icon={<Key size={18} />}
              techStack="OAuth 2.0, JWT, Keycloak"
            />
            
            <DiagramBox 
              title="Authorization Service" 
              description="Role-based access control, permissions"
              color={colors.security}
              icon={<Lock size={18} />}
              techStack="RBAC, Policy Engine"
            />
            
            <DiagramBox 
              title="Data Protection" 
              description="Encryption, compliance, audit logging"
              color={colors.security}
              icon={<Shield size={18} />}
              techStack="AES-256, GDPR Compliance Tools"
            />
          </div>
        </div>
        
        <BiDirectionalConnection />
        
        {/* Data Storage Layer */}
        <div className={styles.layer}>
          <h3 className={styles.sectionTitle}>Data Storage Layer</h3>
          <div className="flex flex-wrap justify-center gap-8">
            <div className="relative mt-8">
              <div className={styles.databaseLabel}>Primary DB</div>
              <DiagramBox 
                title="User & Profile DB" 
                description="User data, learning history, progress tracking"
                color={colors.database}
                icon={<Database size={18} />}
                techStack="PostgreSQL, Redis (caching)"
              />
            </div>
            
            <div className="relative mt-8">
              <div className={styles.databaseLabel}>Content DB</div>
              <DiagramBox 
                title="Training Content DB" 
                description="Structured learning materials, scenarios, assessments"
                color={colors.database}
                icon={<FileText size={18} />}
                techStack="MongoDB, S3 (media storage)"
              />
            </div>
            
            <div className="relative mt-8">
              <div className={styles.databaseLabel}>Analytics DB</div>
              <DiagramBox 
                title="Analytics DB" 
                description="Performance metrics, usage patterns, effectiveness data"
                color={colors.database}
                icon={<BarChart3 size={18} />}
                techStack="ClickHouse, TimescaleDB"
              />
            </div>
            
            <div className="relative mt-8">
              <div className={styles.databaseLabel}>Knowledge DB</div>
              <DiagramBox 
                title="Knowledge Base" 
                description="Food threat management best practices, reference material"
                color={colors.database}
                icon={<BookOpen size={18} />}
                techStack="ElasticSearch, Neo4j"
              />
            </div>
          </div>
        </div>
        
        {/* Additional system notes or details can be added here */}
        <div className="mt-8 border-t pt-4 text-sm text-gray-700">
          <h3 className="font-semibold mb-2">Data Flow Summary</h3>
          <ol className="list-decimal pl-5 space-y-2">
            <li>User requests flow through the web application to the API gateway</li>
            <li>API gateway authenticates requests via the security layer before routing to appropriate services</li>
            <li>Core services process requests, retrieving and storing data in the database layer</li>
            <li>LLM service provides AI-powered content recommendations and adaptations</li>
            <li>Integration layer connects with external systems and the main Knowledge Platform</li>
            <li>Analytics engine tracks user interactions and learning outcomes</li>
            <li>Bi-directional communication maintained between layers for real-time responsiveness</li>
          </ol>
          
          <h3 className="font-semibold mt-4 mb-2">Key Technical Characteristics</h3>
          <ul className="list-disc pl-5 space-y-2">
            <li>Microservices architecture for scalability and maintainability</li>
            <li>Event-driven communication for system-wide notifications</li>
            <li>Cache layers implemented at multiple levels for performance optimization</li>
            <li>API-first design enabling future extensibility</li>
            <li>Containerized deployment using Docker and Kubernetes for orchestration</li>
            <li>CI/CD pipeline for automated testing and deployment</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default ArchitectureDiagram; 