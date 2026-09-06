export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      agenda_item_attachments: {
        Row: {
          agenda_item_id: string
          char_count: number | null
          created_at: string | null
          document_id: string | null
          extracted_text: string | null
          filename: string
          id: string
          mime_type: string | null
          source_content_sha256: string | null
          source_retired_at: string | null
          source_revision_sha256: string | null
          source_url: string | null
        }
        Insert: {
          agenda_item_id: string
          char_count?: number | null
          created_at?: string | null
          document_id?: string | null
          extracted_text?: string | null
          filename: string
          id?: string
          mime_type?: string | null
          source_content_sha256?: string | null
          source_retired_at?: string | null
          source_revision_sha256?: string | null
          source_url?: string | null
        }
        Update: {
          agenda_item_id?: string
          char_count?: number | null
          created_at?: string | null
          document_id?: string | null
          extracted_text?: string | null
          filename?: string
          id?: string
          mime_type?: string | null
          source_content_sha256?: string | null
          source_retired_at?: string | null
          source_revision_sha256?: string | null
          source_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agenda_item_attachments_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agenda_item_attachments_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
        ]
      }
      agenda_items: {
        Row: {
          agenda_source_authority: string
          agenda_source_retired_at: string | null
          agenda_source_revision_sha256: string | null
          ai_comment_summary: string | null
          category: string | null
          continued_from: string | null
          continued_to: string | null
          created_at: string
          department: string | null
          description: string | null
          discussion_duration_minutes: number | null
          financial_amount: string | null
          id: string
          is_consent_calendar: boolean
          item_number: string
          legal_framework: string | null
          legal_framework_classified_at: string | null
          legal_framework_source: string | null
          meeting_id: string
          party_entities: Json | null
          plain_language_generated_at: string | null
          plain_language_model: string | null
          plain_language_summary: string | null
          plain_language_summary_provenance: Json | null
          proceeding_classification_attempts: number
          proceeding_classification_claim_expires_at: string | null
          proceeding_classification_claim_token: string | null
          proceeding_classification_dead_lettered_at: string | null
          proceeding_classification_last_attempted_at: string | null
          proceeding_classification_last_error: string | null
          proceeding_type: string | null
          public_comment_count: number | null
          resolution_number: string | null
          staff_contact: string | null
          summary_headline: string | null
          title: string
          topic_label: string | null
          was_pulled_from_consent: boolean
        }
        Insert: {
          agenda_source_authority?: string
          agenda_source_retired_at?: string | null
          agenda_source_revision_sha256?: string | null
          ai_comment_summary?: string | null
          category?: string | null
          continued_from?: string | null
          continued_to?: string | null
          created_at?: string
          department?: string | null
          description?: string | null
          discussion_duration_minutes?: number | null
          financial_amount?: string | null
          id?: string
          is_consent_calendar?: boolean
          item_number: string
          legal_framework?: string | null
          legal_framework_classified_at?: string | null
          legal_framework_source?: string | null
          meeting_id: string
          party_entities?: Json | null
          plain_language_generated_at?: string | null
          plain_language_model?: string | null
          plain_language_summary?: string | null
          plain_language_summary_provenance?: Json | null
          proceeding_classification_attempts?: number
          proceeding_classification_claim_expires_at?: string | null
          proceeding_classification_claim_token?: string | null
          proceeding_classification_dead_lettered_at?: string | null
          proceeding_classification_last_attempted_at?: string | null
          proceeding_classification_last_error?: string | null
          proceeding_type?: string | null
          public_comment_count?: number | null
          resolution_number?: string | null
          staff_contact?: string | null
          summary_headline?: string | null
          title: string
          topic_label?: string | null
          was_pulled_from_consent?: boolean
        }
        Update: {
          agenda_source_authority?: string
          agenda_source_retired_at?: string | null
          agenda_source_revision_sha256?: string | null
          ai_comment_summary?: string | null
          category?: string | null
          continued_from?: string | null
          continued_to?: string | null
          created_at?: string
          department?: string | null
          description?: string | null
          discussion_duration_minutes?: number | null
          financial_amount?: string | null
          id?: string
          is_consent_calendar?: boolean
          item_number?: string
          legal_framework?: string | null
          legal_framework_classified_at?: string | null
          legal_framework_source?: string | null
          meeting_id?: string
          party_entities?: Json | null
          plain_language_generated_at?: string | null
          plain_language_model?: string | null
          plain_language_summary?: string | null
          plain_language_summary_provenance?: Json | null
          proceeding_classification_attempts?: number
          proceeding_classification_claim_expires_at?: string | null
          proceeding_classification_claim_token?: string | null
          proceeding_classification_dead_lettered_at?: string | null
          proceeding_classification_last_attempted_at?: string | null
          proceeding_classification_last_error?: string | null
          proceeding_type?: string | null
          public_comment_count?: number | null
          resolution_number?: string | null
          staff_contact?: string | null
          summary_headline?: string | null
          title?: string
          topic_label?: string | null
          was_pulled_from_consent?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "agenda_items_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      agenda_items_embeddings: {
        Row: {
          embedding: unknown
          embedding_generated_at: string
          embedding_model: string
          id: string
        }
        Insert: {
          embedding: unknown
          embedding_generated_at?: string
          embedding_model: string
          id: string
        }
        Update: {
          embedding?: unknown
          embedding_generated_at?: string
          embedding_model?: string
          id?: string
        }
        Relationships: [
          {
            foreignKeyName: "agenda_items_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agenda_items_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
        ]
      }
      behested_payments: {
        Row: {
          amount: number | null
          city_fips: string
          created_at: string
          description: string | null
          filing_date: string | null
          filing_id: string | null
          id: string
          metadata: Json
          official_id: string | null
          official_name: string
          payee_description: string | null
          payee_name: string
          payment_date: string | null
          payor_city: string | null
          payor_name: string
          payor_state: string | null
          source: string
          source_identifier: string | null
          source_url: string | null
          updated_at: string
        }
        Insert: {
          amount?: number | null
          city_fips: string
          created_at?: string
          description?: string | null
          filing_date?: string | null
          filing_id?: string | null
          id?: string
          metadata?: Json
          official_id?: string | null
          official_name: string
          payee_description?: string | null
          payee_name: string
          payment_date?: string | null
          payor_city?: string | null
          payor_name: string
          payor_state?: string | null
          source?: string
          source_identifier?: string | null
          source_url?: string | null
          updated_at?: string
        }
        Update: {
          amount?: number | null
          city_fips?: string
          created_at?: string
          description?: string | null
          filing_date?: string | null
          filing_id?: string | null
          id?: string
          metadata?: Json
          official_id?: string | null
          official_name?: string
          payee_description?: string | null
          payee_name?: string
          payment_date?: string | null
          payor_city?: string | null
          payor_name?: string
          payor_state?: string | null
          source?: string
          source_identifier?: string | null
          source_url?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "behested_payments_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      bodies: {
        Row: {
          body_type: string
          city_fips: string
          commission_id: string | null
          created_at: string
          id: string
          is_active: boolean
          is_elected: boolean
          meeting_schedule: string | null
          name: string
          num_seats: number | null
          parent_body_id: string | null
          short_name: string | null
        }
        Insert: {
          body_type: string
          city_fips: string
          commission_id?: string | null
          created_at?: string
          id?: string
          is_active?: boolean
          is_elected?: boolean
          meeting_schedule?: string | null
          name: string
          num_seats?: number | null
          parent_body_id?: string | null
          short_name?: string | null
        }
        Update: {
          body_type?: string
          city_fips?: string
          commission_id?: string | null
          created_at?: string
          id?: string
          is_active?: boolean
          is_elected?: boolean
          meeting_schedule?: string | null
          name?: string
          num_seats?: number | null
          parent_body_id?: string | null
          short_name?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "bodies_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "bodies_commission_id_fkey"
            columns: ["commission_id"]
            isOneToOne: false
            referencedRelation: "commissions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "bodies_commission_id_fkey"
            columns: ["commission_id"]
            isOneToOne: false
            referencedRelation: "v_commission_staleness"
            referencedColumns: ["commission_id"]
          },
          {
            foreignKeyName: "bodies_parent_body_id_fkey"
            columns: ["parent_body_id"]
            isOneToOne: false
            referencedRelation: "bodies"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "bodies_parent_body_id_fkey"
            columns: ["parent_body_id"]
            isOneToOne: false
            referencedRelation: "v_body_meeting_counts"
            referencedColumns: ["body_id"]
          },
        ]
      }
      business_entities: {
        Row: {
          agent_address: string | null
          agent_name: string | null
          city_fips: string
          confidence_score: number | null
          created_at: string
          current_status: string | null
          dissolution_date: string | null
          entity_name: string
          entity_number: string | null
          entity_type: string | null
          extracted_at: string
          id: string
          incorporation_date: string | null
          jurisdiction_code: string
          opencorporates_url: string | null
          raw_response: Json | null
          registered_address: string | null
          retrieved_at: string
          source_publisher: string
          source_tier: number
          source_url: string
          updated_at: string
        }
        Insert: {
          agent_address?: string | null
          agent_name?: string | null
          city_fips: string
          confidence_score?: number | null
          created_at?: string
          current_status?: string | null
          dissolution_date?: string | null
          entity_name: string
          entity_number?: string | null
          entity_type?: string | null
          extracted_at?: string
          id?: string
          incorporation_date?: string | null
          jurisdiction_code?: string
          opencorporates_url?: string | null
          raw_response?: Json | null
          registered_address?: string | null
          retrieved_at: string
          source_publisher?: string
          source_tier?: number
          source_url: string
          updated_at?: string
        }
        Update: {
          agent_address?: string | null
          agent_name?: string | null
          city_fips?: string
          confidence_score?: number | null
          created_at?: string
          current_status?: string | null
          dissolution_date?: string | null
          entity_name?: string
          entity_number?: string | null
          entity_type?: string | null
          extracted_at?: string
          id?: string
          incorporation_date?: string | null
          jurisdiction_code?: string
          opencorporates_url?: string | null
          raw_response?: Json | null
          registered_address?: string | null
          retrieved_at?: string
          source_publisher?: string
          source_tier?: number
          source_url?: string
          updated_at?: string
        }
        Relationships: []
      }
      business_entity_officers: {
        Row: {
          business_entity_id: string
          created_at: string
          end_date: string | null
          id: string
          is_inactive: boolean | null
          officer_name: string
          opencorporates_officer_id: number | null
          position: string | null
          retrieved_at: string
          source_url: string
          start_date: string | null
        }
        Insert: {
          business_entity_id: string
          created_at?: string
          end_date?: string | null
          id?: string
          is_inactive?: boolean | null
          officer_name: string
          opencorporates_officer_id?: number | null
          position?: string | null
          retrieved_at: string
          source_url: string
          start_date?: string | null
        }
        Update: {
          business_entity_id?: string
          created_at?: string
          end_date?: string | null
          id?: string
          is_inactive?: boolean | null
          officer_name?: string
          opencorporates_officer_id?: number | null
          position?: string | null
          retrieved_at?: string
          source_url?: string
          start_date?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "business_entity_officers_business_entity_id_fkey"
            columns: ["business_entity_id"]
            isOneToOne: false
            referencedRelation: "business_entities"
            referencedColumns: ["id"]
          },
        ]
      }
      cities: {
        Row: {
          charter_type: string | null
          clerk_email: string | null
          council_size: number | null
          county: string | null
          created_at: string
          fips_code: string
          name: string
          population: number | null
          state: string
          timezone: string
          website_url: string | null
        }
        Insert: {
          charter_type?: string | null
          clerk_email?: string | null
          council_size?: number | null
          county?: string | null
          created_at?: string
          fips_code: string
          name: string
          population?: number | null
          state: string
          timezone?: string
          website_url?: string | null
        }
        Update: {
          charter_type?: string | null
          clerk_email?: string | null
          council_size?: number | null
          county?: string | null
          created_at?: string
          fips_code?: string
          name?: string
          population?: number | null
          state?: string
          timezone?: string
          website_url?: string | null
        }
        Relationships: []
      }
      city_code_cases: {
        Row: {
          case_location: string | null
          case_subtype: string | null
          case_type: string | null
          city_fips: string
          closed_date: string | null
          created_at: string
          date_corrected: string | null
          date_observed: string | null
          id: string
          neighborhood_council: string | null
          opened_date: string | null
          site_address: string | null
          site_apn: string | null
          site_zip: string | null
          socrata_row_id: string | null
          source: string
          status: string | null
          updated_at: string
          violation: string | null
          violation_type: string | null
        }
        Insert: {
          case_location?: string | null
          case_subtype?: string | null
          case_type?: string | null
          city_fips: string
          closed_date?: string | null
          created_at?: string
          date_corrected?: string | null
          date_observed?: string | null
          id?: string
          neighborhood_council?: string | null
          opened_date?: string | null
          site_address?: string | null
          site_apn?: string | null
          site_zip?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
          violation?: string | null
          violation_type?: string | null
        }
        Update: {
          case_location?: string | null
          case_subtype?: string | null
          case_type?: string | null
          city_fips?: string
          closed_date?: string | null
          created_at?: string
          date_corrected?: string | null
          date_observed?: string | null
          id?: string
          neighborhood_council?: string | null
          opened_date?: string | null
          site_address?: string | null
          site_apn?: string | null
          site_zip?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
          violation?: string | null
          violation_type?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "city_code_cases_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_contracts: {
        Row: {
          annual_cost: number | null
          approval_action: string | null
          approval_date: string | null
          awarding_body: string | null
          city_fips: string
          confidence_score: number | null
          contract_number: string | null
          contract_type: string | null
          created_at: string
          department: string | null
          description: string | null
          expiration_date: string | null
          extracted_at: string
          id: string
          source_tier: number
          source_url: string
          total_cost: number | null
          updated_at: string
          vendor_name: string
        }
        Insert: {
          annual_cost?: number | null
          approval_action?: string | null
          approval_date?: string | null
          awarding_body?: string | null
          city_fips: string
          confidence_score?: number | null
          contract_number?: string | null
          contract_type?: string | null
          created_at?: string
          department?: string | null
          description?: string | null
          expiration_date?: string | null
          extracted_at?: string
          id?: string
          source_tier?: number
          source_url: string
          total_cost?: number | null
          updated_at?: string
          vendor_name: string
        }
        Update: {
          annual_cost?: number | null
          approval_action?: string | null
          approval_date?: string | null
          awarding_body?: string | null
          city_fips?: string
          confidence_score?: number | null
          contract_number?: string | null
          contract_type?: string | null
          created_at?: string
          department?: string | null
          description?: string | null
          expiration_date?: string | null
          extracted_at?: string
          id?: string
          source_tier?: number
          source_url?: string
          total_cost?: number | null
          updated_at?: string
          vendor_name?: string
        }
        Relationships: []
      }
      city_employees: {
        Row: {
          annual_salary: number | null
          city_fips: string
          created_at: string
          department: string | null
          fiscal_year: string | null
          hierarchy_level: number
          id: string
          is_current: boolean
          is_department_head: boolean
          job_title: string | null
          name: string
          normalized_name: string
          socrata_record_id: string | null
          source: string
          total_compensation: number | null
          updated_at: string
        }
        Insert: {
          annual_salary?: number | null
          city_fips: string
          created_at?: string
          department?: string | null
          fiscal_year?: string | null
          hierarchy_level?: number
          id?: string
          is_current?: boolean
          is_department_head?: boolean
          job_title?: string | null
          name: string
          normalized_name: string
          socrata_record_id?: string | null
          source?: string
          total_compensation?: number | null
          updated_at?: string
        }
        Update: {
          annual_salary?: number | null
          city_fips?: string
          created_at?: string
          department?: string | null
          fiscal_year?: string | null
          hierarchy_level?: number
          id?: string
          is_current?: boolean
          is_department_head?: boolean
          job_title?: string | null
          name?: string
          normalized_name?: string
          socrata_record_id?: string | null
          source?: string
          total_compensation?: number | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "city_employees_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_expenditures: {
        Row: {
          amount: number | null
          city_fips: string
          created_at: string
          department: string | null
          description: string | null
          expenditure_date: string | null
          fiscal_year: string | null
          fund: string | null
          id: string
          normalized_vendor: string | null
          socrata_row_id: string | null
          source: string
          updated_at: string
          vendor_name: string | null
        }
        Insert: {
          amount?: number | null
          city_fips: string
          created_at?: string
          department?: string | null
          description?: string | null
          expenditure_date?: string | null
          fiscal_year?: string | null
          fund?: string | null
          id?: string
          normalized_vendor?: string | null
          socrata_row_id?: string | null
          source?: string
          updated_at?: string
          vendor_name?: string | null
        }
        Update: {
          amount?: number | null
          city_fips?: string
          created_at?: string
          department?: string | null
          description?: string | null
          expenditure_date?: string | null
          fiscal_year?: string | null
          fund?: string | null
          id?: string
          normalized_vendor?: string | null
          socrata_row_id?: string | null
          source?: string
          updated_at?: string
          vendor_name?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "city_expenditures_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_licenses: {
        Row: {
          business_start_date: string | null
          business_type: string | null
          city_fips: string
          classification: string | null
          company: string | null
          company_dba: string | null
          created_at: string
          employees: number | null
          id: string
          license_expired: string | null
          license_issued: string | null
          loc_address: string | null
          loc_city: string | null
          loc_zip: string | null
          neighborhood_council: string | null
          normalized_company: string | null
          ownership_type: string | null
          sic_code: string | null
          site_address: string | null
          site_apn: string | null
          socrata_row_id: string | null
          source: string
          status: string | null
          updated_at: string
        }
        Insert: {
          business_start_date?: string | null
          business_type?: string | null
          city_fips: string
          classification?: string | null
          company?: string | null
          company_dba?: string | null
          created_at?: string
          employees?: number | null
          id?: string
          license_expired?: string | null
          license_issued?: string | null
          loc_address?: string | null
          loc_city?: string | null
          loc_zip?: string | null
          neighborhood_council?: string | null
          normalized_company?: string | null
          ownership_type?: string | null
          sic_code?: string | null
          site_address?: string | null
          site_apn?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
        }
        Update: {
          business_start_date?: string | null
          business_type?: string | null
          city_fips?: string
          classification?: string | null
          company?: string | null
          company_dba?: string | null
          created_at?: string
          employees?: number | null
          id?: string
          license_expired?: string | null
          license_issued?: string | null
          loc_address?: string | null
          loc_city?: string | null
          loc_zip?: string | null
          neighborhood_council?: string | null
          normalized_company?: string | null
          ownership_type?: string | null
          sic_code?: string | null
          site_address?: string | null
          site_apn?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "city_licenses_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_permits: {
        Row: {
          applied_by: string | null
          applied_date: string | null
          approved_date: string | null
          building_sqft: number | null
          city_fips: string
          created_at: string
          description: string | null
          expired_date: string | null
          fees_charged: number | null
          fees_paid: number | null
          finaled_date: string | null
          id: string
          issued_date: string | null
          job_value: number | null
          permit_no: string | null
          permit_subtype: string | null
          permit_type: string | null
          project_number: string | null
          situs_address: string | null
          situs_apn: string | null
          socrata_row_id: string | null
          source: string
          status: string | null
          units: number | null
          updated_at: string
        }
        Insert: {
          applied_by?: string | null
          applied_date?: string | null
          approved_date?: string | null
          building_sqft?: number | null
          city_fips: string
          created_at?: string
          description?: string | null
          expired_date?: string | null
          fees_charged?: number | null
          fees_paid?: number | null
          finaled_date?: string | null
          id?: string
          issued_date?: string | null
          job_value?: number | null
          permit_no?: string | null
          permit_subtype?: string | null
          permit_type?: string | null
          project_number?: string | null
          situs_address?: string | null
          situs_apn?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          units?: number | null
          updated_at?: string
        }
        Update: {
          applied_by?: string | null
          applied_date?: string | null
          approved_date?: string | null
          building_sqft?: number | null
          city_fips?: string
          created_at?: string
          description?: string | null
          expired_date?: string | null
          fees_charged?: number | null
          fees_paid?: number | null
          finaled_date?: string | null
          id?: string
          issued_date?: string | null
          job_value?: number | null
          permit_no?: string | null
          permit_subtype?: string | null
          permit_type?: string | null
          project_number?: string | null
          situs_address?: string | null
          situs_apn?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          units?: number | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "city_permits_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_projects: {
        Row: {
          affordability_level_applied: string | null
          affordability_level_approved: string | null
          applied_by: string | null
          applied_date: string | null
          approved_by: string | null
          approved_date: string | null
          city_fips: string
          closed_date: string | null
          created_at: string
          description: string | null
          expired_date: string | null
          id: string
          land_use: string | null
          latitude: number | null
          longitude: number | null
          neighborhood_council: string | null
          occupancy_description: string | null
          parent_project_no: string | null
          project_name: string | null
          project_no: string | null
          project_subtype: string | null
          project_type: string | null
          resolution_no: string | null
          site_address: string | null
          site_apn: string | null
          site_zip: string | null
          socrata_row_id: string | null
          source: string
          status: string | null
          status_date: string | null
          updated_at: string
          zoning_code: string | null
        }
        Insert: {
          affordability_level_applied?: string | null
          affordability_level_approved?: string | null
          applied_by?: string | null
          applied_date?: string | null
          approved_by?: string | null
          approved_date?: string | null
          city_fips: string
          closed_date?: string | null
          created_at?: string
          description?: string | null
          expired_date?: string | null
          id?: string
          land_use?: string | null
          latitude?: number | null
          longitude?: number | null
          neighborhood_council?: string | null
          occupancy_description?: string | null
          parent_project_no?: string | null
          project_name?: string | null
          project_no?: string | null
          project_subtype?: string | null
          project_type?: string | null
          resolution_no?: string | null
          site_address?: string | null
          site_apn?: string | null
          site_zip?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          status_date?: string | null
          updated_at?: string
          zoning_code?: string | null
        }
        Update: {
          affordability_level_applied?: string | null
          affordability_level_approved?: string | null
          applied_by?: string | null
          applied_date?: string | null
          approved_by?: string | null
          approved_date?: string | null
          city_fips?: string
          closed_date?: string | null
          created_at?: string
          description?: string | null
          expired_date?: string | null
          id?: string
          land_use?: string | null
          latitude?: number | null
          longitude?: number | null
          neighborhood_council?: string | null
          occupancy_description?: string | null
          parent_project_no?: string | null
          project_name?: string | null
          project_no?: string | null
          project_subtype?: string | null
          project_type?: string | null
          resolution_no?: string | null
          site_address?: string | null
          site_apn?: string | null
          site_zip?: string | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          status_date?: string | null
          updated_at?: string
          zoning_code?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "city_projects_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      city_service_requests: {
        Row: {
          city_fips: string
          completed_date: string | null
          created_at: string
          created_date: string | null
          created_via: string | null
          department: string | null
          description: string | null
          due_date: string | null
          id: string
          issue_address: string | null
          issue_type: string | null
          latitude: number | null
          linked_doc: string | null
          longitude: number | null
          socrata_row_id: string | null
          source: string
          status: string | null
          updated_at: string
        }
        Insert: {
          city_fips: string
          completed_date?: string | null
          created_at?: string
          created_date?: string | null
          created_via?: string | null
          department?: string | null
          description?: string | null
          due_date?: string | null
          id?: string
          issue_address?: string | null
          issue_type?: string | null
          latitude?: number | null
          linked_doc?: string | null
          longitude?: number | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
        }
        Update: {
          city_fips?: string
          completed_date?: string | null
          created_at?: string
          created_date?: string | null
          created_via?: string | null
          department?: string | null
          description?: string | null
          due_date?: string | null
          id?: string
          issue_address?: string | null
          issue_type?: string | null
          latitude?: number | null
          linked_doc?: string | null
          longitude?: number | null
          socrata_row_id?: string | null
          source?: string
          status?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "city_service_requests_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      closed_session_items: {
        Row: {
          description: string
          id: string
          item_number: string
          legal_authority: string
          meeting_id: string
          parties: string[] | null
          reportable_action: string | null
        }
        Insert: {
          description: string
          id?: string
          item_number: string
          legal_authority: string
          meeting_id: string
          parties?: string[] | null
          reportable_action?: string | null
        }
        Update: {
          description?: string
          id?: string
          item_number?: string
          legal_authority?: string
          meeting_id?: string
          parties?: string[] | null
          reportable_action?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "closed_session_items_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      comment_theme_assignments: {
        Row: {
          comment_id: string
          confidence: number
          created_at: string
          id: string
          source: string
          theme_id: string
        }
        Insert: {
          comment_id: string
          confidence?: number
          created_at?: string
          id?: string
          source?: string
          theme_id: string
        }
        Update: {
          comment_id?: string
          confidence?: number
          created_at?: string
          id?: string
          source?: string
          theme_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "comment_theme_assignments_comment_id_fkey"
            columns: ["comment_id"]
            isOneToOne: false
            referencedRelation: "public_comments"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "comment_theme_assignments_theme_id_fkey"
            columns: ["theme_id"]
            isOneToOne: false
            referencedRelation: "comment_themes"
            referencedColumns: ["id"]
          },
        ]
      }
      comment_themes: {
        Row: {
          city_fips: string
          created_at: string
          description: string | null
          id: string
          label: string
          merged_into_id: string | null
          slug: string
          status: string
          updated_at: string
        }
        Insert: {
          city_fips?: string
          created_at?: string
          description?: string | null
          id?: string
          label: string
          merged_into_id?: string | null
          slug: string
          status?: string
          updated_at?: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          description?: string | null
          id?: string
          label?: string
          merged_into_id?: string | null
          slug?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "comment_themes_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "comment_themes"
            referencedColumns: ["id"]
          },
        ]
      }
      commission_members: {
        Row: {
          appointed_by: string | null
          appointed_by_official_id: string | null
          city_fips: string
          commission_id: string
          created_at: string
          id: string
          is_current: boolean
          name: string
          normalized_name: string
          role: string
          source: string
          source_meeting_id: string | null
          term_end: string | null
          term_start: string | null
          updated_at: string
          website_stale_since: string | null
        }
        Insert: {
          appointed_by?: string | null
          appointed_by_official_id?: string | null
          city_fips: string
          commission_id: string
          created_at?: string
          id?: string
          is_current?: boolean
          name: string
          normalized_name: string
          role?: string
          source?: string
          source_meeting_id?: string | null
          term_end?: string | null
          term_start?: string | null
          updated_at?: string
          website_stale_since?: string | null
        }
        Update: {
          appointed_by?: string | null
          appointed_by_official_id?: string | null
          city_fips?: string
          commission_id?: string
          created_at?: string
          id?: string
          is_current?: boolean
          name?: string
          normalized_name?: string
          role?: string
          source?: string
          source_meeting_id?: string | null
          term_end?: string | null
          term_start?: string | null
          updated_at?: string
          website_stale_since?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "commission_members_appointed_by_official_id_fkey"
            columns: ["appointed_by_official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commission_members_appointed_by_official_id_fkey"
            columns: ["appointed_by_official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "commission_members_appointed_by_official_id_fkey"
            columns: ["appointed_by_official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
          {
            foreignKeyName: "commission_members_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "commission_members_commission_id_fkey"
            columns: ["commission_id"]
            isOneToOne: false
            referencedRelation: "commissions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commission_members_commission_id_fkey"
            columns: ["commission_id"]
            isOneToOne: false
            referencedRelation: "v_commission_staleness"
            referencedColumns: ["commission_id"]
          },
          {
            foreignKeyName: "commission_members_source_meeting_id_fkey"
            columns: ["source_meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      commissions: {
        Row: {
          appointment_authority: string | null
          archive_center_amid: number | null
          city_fips: string
          commission_type: string
          created_at: string
          escribemeetings_type: string | null
          form700_required: boolean
          id: string
          last_website_scrape: string | null
          meeting_schedule: string | null
          name: string
          num_seats: number | null
          term_length_years: number | null
          website_roster_url: string | null
        }
        Insert: {
          appointment_authority?: string | null
          archive_center_amid?: number | null
          city_fips: string
          commission_type?: string
          created_at?: string
          escribemeetings_type?: string | null
          form700_required?: boolean
          id?: string
          last_website_scrape?: string | null
          meeting_schedule?: string | null
          name: string
          num_seats?: number | null
          term_length_years?: number | null
          website_roster_url?: string | null
        }
        Update: {
          appointment_authority?: string | null
          archive_center_amid?: number | null
          city_fips?: string
          commission_type?: string
          created_at?: string
          escribemeetings_type?: string | null
          form700_required?: boolean
          id?: string
          last_website_scrape?: string | null
          meeting_schedule?: string | null
          name?: string
          num_seats?: number | null
          term_length_years?: number | null
          website_roster_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "commissions_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      committees: {
        Row: {
          candidate_name: string | null
          city_fips: string
          committee_type: string | null
          created_at: string
          election_id: string | null
          filer_id: string | null
          id: string
          name: string
          official_id: string | null
          status: string | null
        }
        Insert: {
          candidate_name?: string | null
          city_fips: string
          committee_type?: string | null
          created_at?: string
          election_id?: string | null
          filer_id?: string | null
          id?: string
          name: string
          official_id?: string | null
          status?: string | null
        }
        Update: {
          candidate_name?: string | null
          city_fips?: string
          committee_type?: string | null
          created_at?: string
          election_id?: string | null
          filer_id?: string | null
          id?: string
          name?: string
          official_id?: string | null
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "committees_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "committees_election_id_fkey"
            columns: ["election_id"]
            isOneToOne: false
            referencedRelation: "elections"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "committees_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "committees_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "committees_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      conflict_flags: {
        Row: {
          agenda_item_id: string | null
          city_fips: string
          confidence: number
          confidence_factors: Json | null
          created_at: string
          data_cutoff_date: string | null
          description: string
          evidence: Json
          false_positive: boolean | null
          flag_type: string
          id: string
          influence_pattern_id: number | null
          is_current: boolean
          legal_reference: string | null
          match_details: Json | null
          meeting_id: string | null
          official_id: string | null
          publication_tier: number | null
          reviewed: boolean
          reviewed_at: string | null
          reviewed_by: string | null
          scan_mode: string | null
          scan_run_id: string | null
          scanner_version: number | null
          significance_assigned_at: string | null
          significance_rationale: string | null
          significance_tier: string | null
          superseded_by: string | null
        }
        Insert: {
          agenda_item_id?: string | null
          city_fips: string
          confidence: number
          confidence_factors?: Json | null
          created_at?: string
          data_cutoff_date?: string | null
          description: string
          evidence?: Json
          false_positive?: boolean | null
          flag_type: string
          id?: string
          influence_pattern_id?: number | null
          is_current?: boolean
          legal_reference?: string | null
          match_details?: Json | null
          meeting_id?: string | null
          official_id?: string | null
          publication_tier?: number | null
          reviewed?: boolean
          reviewed_at?: string | null
          reviewed_by?: string | null
          scan_mode?: string | null
          scan_run_id?: string | null
          scanner_version?: number | null
          significance_assigned_at?: string | null
          significance_rationale?: string | null
          significance_tier?: string | null
          superseded_by?: string | null
        }
        Update: {
          agenda_item_id?: string | null
          city_fips?: string
          confidence?: number
          confidence_factors?: Json | null
          created_at?: string
          data_cutoff_date?: string | null
          description?: string
          evidence?: Json
          false_positive?: boolean | null
          flag_type?: string
          id?: string
          influence_pattern_id?: number | null
          is_current?: boolean
          legal_reference?: string | null
          match_details?: Json | null
          meeting_id?: string | null
          official_id?: string | null
          publication_tier?: number | null
          reviewed?: boolean
          reviewed_at?: string | null
          reviewed_by?: string | null
          scan_mode?: string | null
          scan_run_id?: string | null
          scanner_version?: number | null
          significance_assigned_at?: string | null
          significance_rationale?: string | null
          significance_tier?: string | null
          superseded_by?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "conflict_flags_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "conflict_flags_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
          {
            foreignKeyName: "conflict_flags_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "conflict_flags_influence_pattern_id_fkey"
            columns: ["influence_pattern_id"]
            isOneToOne: false
            referencedRelation: "influence_patterns"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "conflict_flags_influence_pattern_id_fkey"
            columns: ["influence_pattern_id"]
            isOneToOne: false
            referencedRelation: "v_influence_pattern_summary"
            referencedColumns: ["pattern_id"]
          },
          {
            foreignKeyName: "conflict_flags_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "conflict_flags_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "conflict_flags_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "conflict_flags_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
          {
            foreignKeyName: "conflict_flags_scan_run_id_fkey"
            columns: ["scan_run_id"]
            isOneToOne: false
            referencedRelation: "scan_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "conflict_flags_superseded_by_fkey"
            columns: ["superseded_by"]
            isOneToOne: false
            referencedRelation: "conflict_flags"
            referencedColumns: ["id"]
          },
        ]
      }
      contributions: {
        Row: {
          amount: number
          city_fips: string
          committee_id: string
          contribution_date: string
          contribution_type: string
          contributor_type: string | null
          contributor_type_source: string | null
          created_at: string
          document_id: string | null
          donor_id: string
          election_id: string | null
          entity_code: string | null
          filing_id: string | null
          id: string
          schedule: string | null
          source: string
        }
        Insert: {
          amount: number
          city_fips: string
          committee_id: string
          contribution_date: string
          contribution_type: string
          contributor_type?: string | null
          contributor_type_source?: string | null
          created_at?: string
          document_id?: string | null
          donor_id: string
          election_id?: string | null
          entity_code?: string | null
          filing_id?: string | null
          id?: string
          schedule?: string | null
          source: string
        }
        Update: {
          amount?: number
          city_fips?: string
          committee_id?: string
          contribution_date?: string
          contribution_type?: string
          contributor_type?: string | null
          contributor_type_source?: string | null
          created_at?: string
          document_id?: string | null
          donor_id?: string
          election_id?: string | null
          entity_code?: string | null
          filing_id?: string | null
          id?: string
          schedule?: string | null
          source?: string
        }
        Relationships: [
          {
            foreignKeyName: "contributions_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "contributions_committee_id_fkey"
            columns: ["committee_id"]
            isOneToOne: false
            referencedRelation: "committees"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "contributions_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "contributions_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donor_context"
            referencedColumns: ["donor_id"]
          },
          {
            foreignKeyName: "contributions_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "contributions_election_id_fkey"
            columns: ["election_id"]
            isOneToOne: false
            referencedRelation: "elections"
            referencedColumns: ["id"]
          },
        ]
      }
      court_case_matches: {
        Row: {
          case_id: string
          city_fips: string
          confidence: number
          court_party_id: string
          created_at: string
          donor_id: string | null
          entity_name: string
          entity_type: string
          false_positive: boolean | null
          id: string
          match_type: string
          metadata: Json
          official_id: string | null
          reviewed: boolean
          reviewed_at: string | null
        }
        Insert: {
          case_id: string
          city_fips: string
          confidence: number
          court_party_id: string
          created_at?: string
          donor_id?: string | null
          entity_name: string
          entity_type: string
          false_positive?: boolean | null
          id?: string
          match_type: string
          metadata?: Json
          official_id?: string | null
          reviewed?: boolean
          reviewed_at?: string | null
        }
        Update: {
          case_id?: string
          city_fips?: string
          confidence?: number
          court_party_id?: string
          created_at?: string
          donor_id?: string | null
          entity_name?: string
          entity_type?: string
          false_positive?: boolean | null
          id?: string
          match_type?: string
          metadata?: Json
          official_id?: string | null
          reviewed?: boolean
          reviewed_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "court_case_matches_case_id_fkey"
            columns: ["case_id"]
            isOneToOne: false
            referencedRelation: "court_cases"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "court_case_matches_court_party_id_fkey"
            columns: ["court_party_id"]
            isOneToOne: false
            referencedRelation: "court_case_parties"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donor_context"
            referencedColumns: ["donor_id"]
          },
          {
            foreignKeyName: "court_case_matches_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      court_case_parties: {
        Row: {
          attorney: string | null
          case_id: string
          created_at: string
          id: string
          is_organization: boolean
          metadata: Json
          normalized_name: string
          party_name: string
          party_type: string
        }
        Insert: {
          attorney?: string | null
          case_id: string
          created_at?: string
          id?: string
          is_organization?: boolean
          metadata?: Json
          normalized_name: string
          party_name: string
          party_type: string
        }
        Update: {
          attorney?: string | null
          case_id?: string
          created_at?: string
          id?: string
          is_organization?: boolean
          metadata?: Json
          normalized_name?: string
          party_name?: string
          party_type?: string
        }
        Relationships: [
          {
            foreignKeyName: "court_case_parties_case_id_fkey"
            columns: ["case_id"]
            isOneToOne: false
            referencedRelation: "court_cases"
            referencedColumns: ["id"]
          },
        ]
      }
      court_cases: {
        Row: {
          case_category: string | null
          case_number: string
          case_status: string | null
          case_title: string | null
          case_type: string | null
          city_fips: string
          county_fips: string
          court_name: string | null
          created_at: string
          credibility_tier: number
          disposition: string | null
          disposition_date: string | null
          filing_date: string | null
          id: string
          judge: string | null
          metadata: Json
          source: string
          source_url: string | null
          updated_at: string
        }
        Insert: {
          case_category?: string | null
          case_number: string
          case_status?: string | null
          case_title?: string | null
          case_type?: string | null
          city_fips: string
          county_fips: string
          court_name?: string | null
          created_at?: string
          credibility_tier?: number
          disposition?: string | null
          disposition_date?: string | null
          filing_date?: string | null
          id?: string
          judge?: string | null
          metadata?: Json
          source?: string
          source_url?: string | null
          updated_at?: string
        }
        Update: {
          case_category?: string | null
          case_number?: string
          case_status?: string | null
          case_title?: string | null
          case_type?: string | null
          city_fips?: string
          county_fips?: string
          court_name?: string | null
          created_at?: string
          credibility_tier?: number
          disposition?: string | null
          disposition_date?: string | null
          filing_date?: string | null
          id?: string
          judge?: string | null
          metadata?: Json
          source?: string
          source_url?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "court_cases_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      cpra_requests: {
        Row: {
          city_fips: string
          created_at: string
          document_id: string | null
          filed_date: string | null
          id: string
          legal_basis: string | null
          request_text: string
          response_due: string | null
          response_notes: string | null
          status: string
          target_department: string | null
        }
        Insert: {
          city_fips: string
          created_at?: string
          document_id?: string | null
          filed_date?: string | null
          id?: string
          legal_basis?: string | null
          request_text: string
          response_due?: string | null
          response_notes?: string | null
          status?: string
          target_department?: string | null
        }
        Update: {
          city_fips?: string
          created_at?: string
          document_id?: string | null
          filed_date?: string | null
          id?: string
          legal_basis?: string | null
          request_text?: string
          response_due?: string | null
          response_notes?: string | null
          status?: string
          target_department?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "cpra_requests_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "cpra_requests_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      data_sync_log: {
        Row: {
          change_id: string | null
          city_fips: string
          completed_at: string | null
          error_message: string | null
          id: string
          metadata: Json
          pipeline_run_id: string | null
          records_fetched: number | null
          records_new: number | null
          records_updated: number | null
          source: string
          started_at: string
          status: string
          sync_type: string
          triggered_by: string | null
        }
        Insert: {
          change_id?: string | null
          city_fips: string
          completed_at?: string | null
          error_message?: string | null
          id?: string
          metadata?: Json
          pipeline_run_id?: string | null
          records_fetched?: number | null
          records_new?: number | null
          records_updated?: number | null
          source: string
          started_at?: string
          status?: string
          sync_type: string
          triggered_by?: string | null
        }
        Update: {
          change_id?: string | null
          city_fips?: string
          completed_at?: string | null
          error_message?: string | null
          id?: string
          metadata?: Json
          pipeline_run_id?: string | null
          records_fetched?: number | null
          records_new?: number | null
          records_updated?: number | null
          source?: string
          started_at?: string
          status?: string
          sync_type?: string
          triggered_by?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "data_sync_log_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      document_references: {
        Row: {
          created_at: string
          expected_url: string | null
          found: boolean
          id: string
          referenced_description: string
          resolved_document_id: string | null
          source_document_id: string
        }
        Insert: {
          created_at?: string
          expected_url?: string | null
          found?: boolean
          id?: string
          referenced_description: string
          resolved_document_id?: string | null
          source_document_id: string
        }
        Update: {
          created_at?: string
          expected_url?: string | null
          found?: boolean
          id?: string
          referenced_description?: string
          resolved_document_id?: string | null
          source_document_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_references_resolved_document_id_fkey"
            columns: ["resolved_document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_references_source_document_id_fkey"
            columns: ["source_document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          city_fips: string
          content_hash: string | null
          credibility_tier: number
          id: string
          ingested_at: string
          metadata: Json
          mime_type: string | null
          raw_content: string | null
          raw_text: string | null
          source_identifier: string | null
          source_retired_at: string | null
          source_type: string
          source_url: string | null
        }
        Insert: {
          city_fips: string
          content_hash?: string | null
          credibility_tier: number
          id?: string
          ingested_at?: string
          metadata?: Json
          mime_type?: string | null
          raw_content?: string | null
          raw_text?: string | null
          source_identifier?: string | null
          source_retired_at?: string | null
          source_type: string
          source_url?: string | null
        }
        Update: {
          city_fips?: string
          content_hash?: string | null
          credibility_tier?: number
          id?: string
          ingested_at?: string
          metadata?: Json
          mime_type?: string | null
          raw_content?: string | null
          raw_text?: string | null
          source_identifier?: string | null
          source_retired_at?: string | null
          source_type?: string
          source_url?: string | null
        }
        Relationships: []
      }
      donors: {
        Row: {
          address: string | null
          city_fips: string
          contribution_span_days: number | null
          created_at: string
          distinct_recipients: number | null
          donor_pattern: string | null
          employer: string | null
          entity_slug: string | null
          entity_type: string | null
          id: string
          name: string
          normalized_employer: string | null
          normalized_name: string
          occupation: string | null
          total_contributed: number | null
        }
        Insert: {
          address?: string | null
          city_fips: string
          contribution_span_days?: number | null
          created_at?: string
          distinct_recipients?: number | null
          donor_pattern?: string | null
          employer?: string | null
          entity_slug?: string | null
          entity_type?: string | null
          id?: string
          name: string
          normalized_employer?: string | null
          normalized_name: string
          occupation?: string | null
          total_contributed?: number | null
        }
        Update: {
          address?: string | null
          city_fips?: string
          contribution_span_days?: number | null
          created_at?: string
          distinct_recipients?: number | null
          donor_pattern?: string | null
          employer?: string | null
          entity_slug?: string | null
          entity_type?: string | null
          id?: string
          name?: string
          normalized_employer?: string | null
          normalized_name?: string
          occupation?: string | null
          total_contributed?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "donors_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      economic_interests: {
        Row: {
          city_fips: string
          created_at: string
          description: string
          document_id: string | null
          filing_id: string | null
          filing_year: number
          id: string
          interest_type: string
          location: string | null
          official_id: string | null
          schedule: string
          source_url: string | null
          value_range: string | null
        }
        Insert: {
          city_fips: string
          created_at?: string
          description: string
          document_id?: string | null
          filing_id?: string | null
          filing_year: number
          id?: string
          interest_type: string
          location?: string | null
          official_id?: string | null
          schedule: string
          source_url?: string | null
          value_range?: string | null
        }
        Update: {
          city_fips?: string
          created_at?: string
          description?: string
          document_id?: string | null
          filing_id?: string | null
          filing_year?: number
          id?: string
          interest_type?: string
          location?: string | null
          official_id?: string | null
          schedule?: string
          source_url?: string | null
          value_range?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "economic_interests_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "economic_interests_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "economic_interests_filing_id_fkey"
            columns: ["filing_id"]
            isOneToOne: false
            referencedRelation: "form700_filings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "economic_interests_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "economic_interests_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "economic_interests_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      election_candidates: {
        Row: {
          candidate_name: string
          city_fips: string
          committee_id: string | null
          confidence_score: number | null
          created_at: string
          election_id: string
          extracted_at: string | null
          fppc_id: string | null
          id: string
          is_incumbent: boolean
          normalized_name: string
          office_sought: string
          official_id: string | null
          party: string | null
          qualification_date: string | null
          source: string
          source_tier: number | null
          source_url: string | null
          status: string
          updated_at: string
        }
        Insert: {
          candidate_name: string
          city_fips: string
          committee_id?: string | null
          confidence_score?: number | null
          created_at?: string
          election_id: string
          extracted_at?: string | null
          fppc_id?: string | null
          id?: string
          is_incumbent?: boolean
          normalized_name: string
          office_sought: string
          official_id?: string | null
          party?: string | null
          qualification_date?: string | null
          source?: string
          source_tier?: number | null
          source_url?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          candidate_name?: string
          city_fips?: string
          committee_id?: string | null
          confidence_score?: number | null
          created_at?: string
          election_id?: string
          extracted_at?: string | null
          fppc_id?: string | null
          id?: string
          is_incumbent?: boolean
          normalized_name?: string
          office_sought?: string
          official_id?: string | null
          party?: string | null
          qualification_date?: string | null
          source?: string
          source_tier?: number | null
          source_url?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "election_candidates_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "election_candidates_committee_id_fkey"
            columns: ["committee_id"]
            isOneToOne: false
            referencedRelation: "committees"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "election_candidates_election_id_fkey"
            columns: ["election_id"]
            isOneToOne: false
            referencedRelation: "elections"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "election_candidates_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "election_candidates_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "election_candidates_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      elections: {
        Row: {
          city_fips: string
          created_at: string
          election_date: string
          election_name: string | null
          election_type: string
          filing_deadline: string | null
          id: string
          jurisdiction: string | null
          notes: string | null
          source: string
          source_tier: number
          source_url: string | null
          updated_at: string
        }
        Insert: {
          city_fips: string
          created_at?: string
          election_date: string
          election_name?: string | null
          election_type: string
          filing_deadline?: string | null
          id?: string
          jurisdiction?: string | null
          notes?: string | null
          source?: string
          source_tier?: number
          source_url?: string | null
          updated_at?: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          election_date?: string
          election_name?: string | null
          election_type?: string
          filing_deadline?: string | null
          id?: string
          jurisdiction?: string | null
          notes?: string | null
          source?: string
          source_tier?: number
          source_url?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "elections_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      email_deliveries: {
        Row: {
          attempt_count: number
          city_fips: string
          claim_token: string | null
          content_key: string
          created_at: string
          delivery_kind: string
          failure_kind: string | null
          first_attempt_at: string | null
          id: string
          last_error: string | null
          lease_expires_at: string | null
          next_attempt_at: string | null
          payload_sha256: string | null
          provider_message_id: string | null
          sent_at: string | null
          status: string
          subscriber_id: string
          subscription_activation_id: string | null
          updated_at: string
        }
        Insert: {
          attempt_count?: number
          city_fips?: string
          claim_token?: string | null
          content_key: string
          created_at?: string
          delivery_kind: string
          failure_kind?: string | null
          first_attempt_at?: string | null
          id?: string
          last_error?: string | null
          lease_expires_at?: string | null
          next_attempt_at?: string | null
          payload_sha256?: string | null
          provider_message_id?: string | null
          sent_at?: string | null
          status?: string
          subscriber_id: string
          subscription_activation_id?: string | null
          updated_at?: string
        }
        Update: {
          attempt_count?: number
          city_fips?: string
          claim_token?: string | null
          content_key?: string
          created_at?: string
          delivery_kind?: string
          failure_kind?: string | null
          first_attempt_at?: string | null
          id?: string
          last_error?: string | null
          lease_expires_at?: string | null
          next_attempt_at?: string | null
          payload_sha256?: string | null
          provider_message_id?: string | null
          sent_at?: string | null
          status?: string
          subscriber_id?: string
          subscription_activation_id?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "email_deliveries_subscriber_id_fkey"
            columns: ["subscriber_id"]
            isOneToOne: false
            referencedRelation: "email_subscribers"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "email_deliveries_subscription_activation_id_fkey"
            columns: ["subscription_activation_id"]
            isOneToOne: false
            referencedRelation: "subscription_activations"
            referencedColumns: ["id"]
          },
        ]
      }
      email_preferences: {
        Row: {
          city_fips: string
          created_at: string
          id: string
          preference_type: string
          preference_value: string
          subscriber_id: string
        }
        Insert: {
          city_fips?: string
          created_at?: string
          id?: string
          preference_type: string
          preference_value: string
          subscriber_id: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          id?: string
          preference_type?: string
          preference_value?: string
          subscriber_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "email_preferences_subscriber_id_fkey"
            columns: ["subscriber_id"]
            isOneToOne: false
            referencedRelation: "email_subscribers"
            referencedColumns: ["id"]
          },
        ]
      }
      email_subscribers: {
        Row: {
          city_fips: string
          current_activation_at: string | null
          current_activation_id: string | null
          current_activation_surface: string | null
          email: string
          id: string
          last_orientation_meeting_id: string | null
          metadata: Json | null
          name: string | null
          source: string
          status: string
          subscribed_at: string
          unsubscribe_token: string
          unsubscribed_at: string | null
        }
        Insert: {
          city_fips?: string
          current_activation_at?: string | null
          current_activation_id?: string | null
          current_activation_surface?: string | null
          email: string
          id?: string
          last_orientation_meeting_id?: string | null
          metadata?: Json | null
          name?: string | null
          source?: string
          status?: string
          subscribed_at?: string
          unsubscribe_token?: string
          unsubscribed_at?: string | null
        }
        Update: {
          city_fips?: string
          current_activation_at?: string | null
          current_activation_id?: string | null
          current_activation_surface?: string | null
          email?: string
          id?: string
          last_orientation_meeting_id?: string | null
          metadata?: Json | null
          name?: string | null
          source?: string
          status?: string
          subscribed_at?: string
          unsubscribe_token?: string
          unsubscribed_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "email_subscribers_last_orientation_meeting_id_fkey"
            columns: ["last_orientation_meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      entity_links: {
        Row: {
          city_fips: string
          confidence: number
          created_at: string
          donor_id: string | null
          effective_date: string | null
          id: string
          metadata: Json
          normalized_person_name: string
          official_id: string | null
          organization_id: string
          person_name: string
          role: string
          role_detail: string | null
          source: string
          source_url: string | null
        }
        Insert: {
          city_fips: string
          confidence?: number
          created_at?: string
          donor_id?: string | null
          effective_date?: string | null
          id?: string
          metadata?: Json
          normalized_person_name: string
          official_id?: string | null
          organization_id: string
          person_name: string
          role: string
          role_detail?: string | null
          source: string
          source_url?: string | null
        }
        Update: {
          city_fips?: string
          confidence?: number
          created_at?: string
          donor_id?: string | null
          effective_date?: string | null
          id?: string
          metadata?: Json
          normalized_person_name?: string
          official_id?: string | null
          organization_id?: string
          person_name?: string
          role?: string
          role_detail?: string | null
          source?: string
          source_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "entity_links_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "entity_links_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donor_context"
            referencedColumns: ["donor_id"]
          },
          {
            foreignKeyName: "entity_links_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
          {
            foreignKeyName: "entity_links_organization_id_fkey"
            columns: ["organization_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      entity_name_matches: {
        Row: {
          business_entity_id: string | null
          created_at: string
          id: string
          match_confidence: number
          match_method: string
          reviewed: boolean | null
          reviewed_at: string | null
          source_name: string
          source_record_id: string
          source_table: string
        }
        Insert: {
          business_entity_id?: string | null
          created_at?: string
          id?: string
          match_confidence: number
          match_method: string
          reviewed?: boolean | null
          reviewed_at?: string | null
          source_name: string
          source_record_id: string
          source_table: string
        }
        Update: {
          business_entity_id?: string | null
          created_at?: string
          id?: string
          match_confidence?: number
          match_method?: string
          reviewed?: boolean | null
          reviewed_at?: string | null
          source_name?: string
          source_record_id?: string
          source_table?: string
        }
        Relationships: [
          {
            foreignKeyName: "entity_name_matches_business_entity_id_fkey"
            columns: ["business_entity_id"]
            isOneToOne: false
            referencedRelation: "business_entities"
            referencedColumns: ["id"]
          },
        ]
      }
      external_references: {
        Row: {
          confidence: number | null
          created_at: string
          document_id: string
          entity_id: string | null
          entity_name: string | null
          entity_type: string
          excerpt: string | null
          id: string
          mention_type: string | null
          sentiment: string | null
        }
        Insert: {
          confidence?: number | null
          created_at?: string
          document_id: string
          entity_id?: string | null
          entity_name?: string | null
          entity_type: string
          excerpt?: string | null
          id?: string
          mention_type?: string | null
          sentiment?: string | null
        }
        Update: {
          confidence?: number | null
          created_at?: string
          document_id?: string
          entity_id?: string | null
          entity_name?: string | null
          entity_type?: string
          excerpt?: string | null
          id?: string
          mention_type?: string | null
          sentiment?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "external_references_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      extraction_runs: {
        Row: {
          cost_usd: number | null
          document_id: string
          extracted_at: string
          extracted_data: Json
          extraction_model: string
          extraction_prompt_version: string | null
          id: string
          input_tokens: number | null
          is_current: boolean
          output_tokens: number | null
        }
        Insert: {
          cost_usd?: number | null
          document_id: string
          extracted_at?: string
          extracted_data: Json
          extraction_model: string
          extraction_prompt_version?: string | null
          id?: string
          input_tokens?: number | null
          is_current?: boolean
          output_tokens?: number | null
        }
        Update: {
          cost_usd?: number | null
          document_id?: string
          extracted_at?: string
          extracted_data?: Json
          extraction_model?: string
          extraction_prompt_version?: string | null
          id?: string
          input_tokens?: number | null
          is_current?: boolean
          output_tokens?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "extraction_runs_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      filing_period_briefings: {
        Row: {
          city_fips: string
          contributions_considered: number | null
          election_id: string | null
          filed_through: string | null
          generated_at: string
          generator: string
          generator_version: string | null
          id: string
          is_current: boolean
          model_version: string | null
          notes: string | null
          paper_filings_considered: number | null
          period_end: string
          period_kind: string
          period_label: string
          period_start: string
          provenance: Json | null
          publication_tier: string
          section_tiers: Json
          sections: Json
          superseded_at: string | null
        }
        Insert: {
          city_fips: string
          contributions_considered?: number | null
          election_id?: string | null
          filed_through?: string | null
          generated_at?: string
          generator?: string
          generator_version?: string | null
          id?: string
          is_current?: boolean
          model_version?: string | null
          notes?: string | null
          paper_filings_considered?: number | null
          period_end: string
          period_kind: string
          period_label: string
          period_start: string
          provenance?: Json | null
          publication_tier?: string
          section_tiers?: Json
          sections?: Json
          superseded_at?: string | null
        }
        Update: {
          city_fips?: string
          contributions_considered?: number | null
          election_id?: string | null
          filed_through?: string | null
          generated_at?: string
          generator?: string
          generator_version?: string | null
          id?: string
          is_current?: boolean
          model_version?: string | null
          notes?: string | null
          paper_filings_considered?: number | null
          period_end?: string
          period_kind?: string
          period_label?: string
          period_start?: string
          provenance?: Json | null
          publication_tier?: string
          section_tiers?: Json
          sections?: Json
          superseded_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "filing_period_briefings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "filing_period_briefings_election_id_fkey"
            columns: ["election_id"]
            isOneToOne: false
            referencedRelation: "elections"
            referencedColumns: ["id"]
          },
        ]
      }
      form_summary_cache: {
        Row: {
          city_fips: string
          committee: string
          extracted_at: string
          filing_id: string
          summary: Json
          updated_at: string
        }
        Insert: {
          city_fips?: string
          committee: string
          extracted_at?: string
          filing_id: string
          summary: Json
          updated_at?: string
        }
        Update: {
          city_fips?: string
          committee?: string
          extracted_at?: string
          filing_id?: string
          summary?: Json
          updated_at?: string
        }
        Relationships: []
      }
      form700_filings: {
        Row: {
          city_fips: string
          confidence_score: number
          created_at: string
          document_id: string | null
          extracted_at: string
          filer_agency: string | null
          filer_name: string
          filer_position: string | null
          filing_year: number
          id: string
          metadata: Json
          no_interests_declared: boolean
          official_id: string | null
          period_end: string | null
          period_start: string | null
          source: string
          source_tier: number
          source_url: string
          statement_type: string
        }
        Insert: {
          city_fips: string
          confidence_score?: number
          created_at?: string
          document_id?: string | null
          extracted_at?: string
          filer_agency?: string | null
          filer_name: string
          filer_position?: string | null
          filing_year: number
          id?: string
          metadata?: Json
          no_interests_declared?: boolean
          official_id?: string | null
          period_end?: string | null
          period_start?: string | null
          source: string
          source_tier?: number
          source_url: string
          statement_type: string
        }
        Update: {
          city_fips?: string
          confidence_score?: number
          created_at?: string
          document_id?: string | null
          extracted_at?: string
          filer_agency?: string | null
          filer_name?: string
          filer_position?: string | null
          filing_year?: number
          id?: string
          metadata?: Json
          no_interests_declared?: boolean
          official_id?: string | null
          period_end?: string | null
          period_start?: string | null
          source?: string
          source_tier?: number
          source_url?: string
          statement_type?: string
        }
        Relationships: [
          {
            foreignKeyName: "form700_filings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "form700_filings_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "form700_filings_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "form700_filings_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "form700_filings_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      friendly_amendments: {
        Row: {
          accepted: boolean
          description: string
          id: string
          motion_id: string
          proposed_by: string
        }
        Insert: {
          accepted: boolean
          description: string
          id?: string
          motion_id: string
          proposed_by: string
        }
        Update: {
          accepted?: boolean
          description?: string
          id?: string
          motion_id?: string
          proposed_by?: string
        }
        Relationships: [
          {
            foreignKeyName: "friendly_amendments_motion_id_fkey"
            columns: ["motion_id"]
            isOneToOne: false
            referencedRelation: "motions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "friendly_amendments_motion_id_fkey"
            columns: ["motion_id"]
            isOneToOne: false
            referencedRelation: "v_split_votes"
            referencedColumns: ["motion_id"]
          },
        ]
      }
      independent_expenditures: {
        Row: {
          amount: number | null
          candidate_name: string | null
          city_fips: string
          committee_name: string
          created_at: string | null
          description: string | null
          expenditure_code: string | null
          expenditure_date: string | null
          filing_id: string | null
          id: string
          payee_name: string | null
          source: string | null
          support_or_oppose: string | null
        }
        Insert: {
          amount?: number | null
          candidate_name?: string | null
          city_fips: string
          committee_name: string
          created_at?: string | null
          description?: string | null
          expenditure_code?: string | null
          expenditure_date?: string | null
          filing_id?: string | null
          id?: string
          payee_name?: string | null
          source?: string | null
          support_or_oppose?: string | null
        }
        Update: {
          amount?: number | null
          candidate_name?: string | null
          city_fips?: string
          committee_name?: string
          created_at?: string | null
          description?: string | null
          expenditure_code?: string | null
          expenditure_date?: string | null
          filing_id?: string | null
          id?: string
          payee_name?: string | null
          source?: string | null
          support_or_oppose?: string | null
        }
        Relationships: []
      }
      influence_patterns: {
        Row: {
          created_at: string
          description: string
          id: number
          pattern_name: string
          signal_types: string[]
          sort_order: number
          source_doc: string
        }
        Insert: {
          created_at?: string
          description: string
          id?: never
          pattern_name: string
          signal_types?: string[]
          sort_order?: number
          source_doc?: string
        }
        Update: {
          created_at?: string
          description?: string
          id?: never
          pattern_name?: string
          signal_types?: string[]
          sort_order?: number
          source_doc?: string
        }
        Relationships: []
      }
      item_theme_narratives: {
        Row: {
          agenda_item_id: string
          comment_count: number
          confidence: number
          generated_at: string
          id: string
          model: string | null
          narrative: string
          theme_id: string
        }
        Insert: {
          agenda_item_id: string
          comment_count?: number
          confidence?: number
          generated_at?: string
          id?: string
          model?: string | null
          narrative: string
          theme_id: string
        }
        Update: {
          agenda_item_id?: string
          comment_count?: number
          confidence?: number
          generated_at?: string
          id?: string
          model?: string | null
          narrative?: string
          theme_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "item_theme_narratives_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "item_theme_narratives_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
          {
            foreignKeyName: "item_theme_narratives_theme_id_fkey"
            columns: ["theme_id"]
            isOneToOne: false
            referencedRelation: "comment_themes"
            referencedColumns: ["id"]
          },
        ]
      }
      item_topics: {
        Row: {
          agenda_item_id: string
          confidence: number
          created_at: string
          id: string
          source: string
          topic_id: string
        }
        Insert: {
          agenda_item_id: string
          confidence?: number
          created_at?: string
          id?: string
          source?: string
          topic_id: string
        }
        Update: {
          agenda_item_id?: string
          confidence?: number
          created_at?: string
          id?: string
          source?: string
          topic_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "item_topics_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "item_topics_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
          {
            foreignKeyName: "item_topics_topic_id_fkey"
            columns: ["topic_id"]
            isOneToOne: false
            referencedRelation: "topics"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "item_topics_topic_id_fkey"
            columns: ["topic_id"]
            isOneToOne: false
            referencedRelation: "v_topic_stats"
            referencedColumns: ["id"]
          },
        ]
      }
      llm_cost_reservations: {
        Row: {
          actual_cost: number | null
          caller: string
          city_fips: string
          created_at: string
          event_type: string | null
          id: string
          metadata: Json
          model: string
          projected_cost: number
          settled_at: string | null
          status: string
        }
        Insert: {
          actual_cost?: number | null
          caller: string
          city_fips?: string
          created_at?: string
          event_type?: string | null
          id: string
          metadata?: Json
          model: string
          projected_cost: number
          settled_at?: string | null
          status?: string
        }
        Update: {
          actual_cost?: number | null
          caller?: string
          city_fips?: string
          created_at?: string
          event_type?: string | null
          id?: string
          metadata?: Json
          model?: string
          projected_cost?: number
          settled_at?: string | null
          status?: string
        }
        Relationships: []
      }
      lobbyist_document_extractions: {
        Row: {
          ai_generated: boolean
          city_fips: string
          confidence_score: number
          content_sha256: string
          document_id: number
          extracted_at: string
          extraction_model: string
          extraction_provider: string
          prompt_version: string
          records: Json
          source_tier: number
          source_url: string
        }
        Insert: {
          ai_generated?: boolean
          city_fips?: string
          confidence_score: number
          content_sha256: string
          document_id: number
          extracted_at?: string
          extraction_model: string
          extraction_provider: string
          prompt_version: string
          records: Json
          source_tier?: number
          source_url: string
        }
        Update: {
          ai_generated?: boolean
          city_fips?: string
          confidence_score?: number
          content_sha256?: string
          document_id?: number
          extracted_at?: string
          extraction_model?: string
          extraction_provider?: string
          prompt_version?: string
          records?: Json
          source_tier?: number
          source_url?: string
        }
        Relationships: []
      }
      lobbyist_registrations: {
        Row: {
          city_agencies: string | null
          city_fips: string
          client_name: string
          created_at: string
          expiration_date: string | null
          id: string
          lobbyist_address: string | null
          lobbyist_email: string | null
          lobbyist_firm: string | null
          lobbyist_name: string
          lobbyist_phone: string | null
          metadata: Json
          registration_date: string | null
          source: string
          source_identifier: string | null
          source_url: string | null
          status: string | null
          topics: string | null
          updated_at: string
        }
        Insert: {
          city_agencies?: string | null
          city_fips: string
          client_name: string
          created_at?: string
          expiration_date?: string | null
          id?: string
          lobbyist_address?: string | null
          lobbyist_email?: string | null
          lobbyist_firm?: string | null
          lobbyist_name: string
          lobbyist_phone?: string | null
          metadata?: Json
          registration_date?: string | null
          source?: string
          source_identifier?: string | null
          source_url?: string | null
          status?: string | null
          topics?: string | null
          updated_at?: string
        }
        Update: {
          city_agencies?: string | null
          city_fips?: string
          client_name?: string
          created_at?: string
          expiration_date?: string | null
          id?: string
          lobbyist_address?: string | null
          lobbyist_email?: string | null
          lobbyist_firm?: string | null
          lobbyist_name?: string
          lobbyist_phone?: string | null
          metadata?: Json
          registration_date?: string | null
          source?: string
          source_identifier?: string | null
          source_url?: string | null
          status?: string | null
          topics?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "lobbyist_registrations_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      meeting_attendance: {
        Row: {
          body_id: string | null
          id: string
          meeting_id: string
          notes: string | null
          official_id: string
          status: string
        }
        Insert: {
          body_id?: string | null
          id?: string
          meeting_id: string
          notes?: string | null
          official_id: string
          status: string
        }
        Update: {
          body_id?: string | null
          id?: string
          meeting_id?: string
          notes?: string | null
          official_id?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "meeting_attendance_body_id_fkey"
            columns: ["body_id"]
            isOneToOne: false
            referencedRelation: "bodies"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "meeting_attendance_body_id_fkey"
            columns: ["body_id"]
            isOneToOne: false
            referencedRelation: "v_body_meeting_counts"
            referencedColumns: ["body_id"]
          },
          {
            foreignKeyName: "meeting_attendance_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "meeting_attendance_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "meeting_attendance_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "meeting_attendance_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      meetings: {
        Row: {
          adjourned_in_memory_of: string | null
          adjournment_time: string | null
          agenda_item_count: number
          agenda_url: string | null
          body_id: string
          call_to_order_time: string | null
          city_fips: string
          created_at: string
          document_id: string | null
          id: string
          meeting_date: string
          meeting_recap: string | null
          meeting_recap_provenance: Json | null
          meeting_summary: string | null
          meeting_summary_provenance: Json | null
          meeting_type: string
          metadata: Json
          minutes_url: string | null
          next_meeting_date: string | null
          orientation_emailed_at: string | null
          orientation_preview: string | null
          orientation_preview_provenance: Json | null
          presiding_officer: string | null
          recap_emailed_at: string | null
          source_cancelled_at: string | null
          source_meeting_guid: string | null
          transcript_recap: string | null
          transcript_recap_corrected_at: string | null
          transcript_recap_emailed_at: string | null
          transcript_recap_generated_at: string | null
          transcript_recap_provenance: Json | null
          transcript_recap_source: string | null
          video_url: string | null
        }
        Insert: {
          adjourned_in_memory_of?: string | null
          adjournment_time?: string | null
          agenda_item_count?: number
          agenda_url?: string | null
          body_id: string
          call_to_order_time?: string | null
          city_fips: string
          created_at?: string
          document_id?: string | null
          id?: string
          meeting_date: string
          meeting_recap?: string | null
          meeting_recap_provenance?: Json | null
          meeting_summary?: string | null
          meeting_summary_provenance?: Json | null
          meeting_type: string
          metadata?: Json
          minutes_url?: string | null
          next_meeting_date?: string | null
          orientation_emailed_at?: string | null
          orientation_preview?: string | null
          orientation_preview_provenance?: Json | null
          presiding_officer?: string | null
          recap_emailed_at?: string | null
          source_cancelled_at?: string | null
          source_meeting_guid?: string | null
          transcript_recap?: string | null
          transcript_recap_corrected_at?: string | null
          transcript_recap_emailed_at?: string | null
          transcript_recap_generated_at?: string | null
          transcript_recap_provenance?: Json | null
          transcript_recap_source?: string | null
          video_url?: string | null
        }
        Update: {
          adjourned_in_memory_of?: string | null
          adjournment_time?: string | null
          agenda_item_count?: number
          agenda_url?: string | null
          body_id?: string
          call_to_order_time?: string | null
          city_fips?: string
          created_at?: string
          document_id?: string | null
          id?: string
          meeting_date?: string
          meeting_recap?: string | null
          meeting_recap_provenance?: Json | null
          meeting_summary?: string | null
          meeting_summary_provenance?: Json | null
          meeting_type?: string
          metadata?: Json
          minutes_url?: string | null
          next_meeting_date?: string | null
          orientation_emailed_at?: string | null
          orientation_preview?: string | null
          orientation_preview_provenance?: Json | null
          presiding_officer?: string | null
          recap_emailed_at?: string | null
          source_cancelled_at?: string | null
          source_meeting_guid?: string | null
          transcript_recap?: string | null
          transcript_recap_corrected_at?: string | null
          transcript_recap_emailed_at?: string | null
          transcript_recap_generated_at?: string | null
          transcript_recap_provenance?: Json | null
          transcript_recap_source?: string | null
          video_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "meetings_body_id_fkey"
            columns: ["body_id"]
            isOneToOne: false
            referencedRelation: "bodies"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "meetings_body_id_fkey"
            columns: ["body_id"]
            isOneToOne: false
            referencedRelation: "v_body_meeting_counts"
            referencedColumns: ["body_id"]
          },
          {
            foreignKeyName: "meetings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "meetings_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      meetings_embeddings: {
        Row: {
          embedding: unknown
          embedding_generated_at: string
          embedding_model: string
          id: string
        }
        Insert: {
          embedding: unknown
          embedding_generated_at?: string
          embedding_model: string
          id: string
        }
        Update: {
          embedding?: unknown
          embedding_generated_at?: string
          embedding_model?: string
          id?: string
        }
        Relationships: [
          {
            foreignKeyName: "meetings_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      motions: {
        Row: {
          agenda_item_id: string
          created_at: string
          id: string
          motion_text: string
          motion_type: string
          moved_by: string | null
          resolution_number: string | null
          result: string
          seconded_by: string | null
          sequence_number: number
          source: string | null
          vote_explainer: string | null
          vote_explainer_generated_at: string | null
          vote_explainer_model: string | null
          vote_tally: string | null
        }
        Insert: {
          agenda_item_id: string
          created_at?: string
          id?: string
          motion_text: string
          motion_type: string
          moved_by?: string | null
          resolution_number?: string | null
          result: string
          seconded_by?: string | null
          sequence_number?: number
          source?: string | null
          vote_explainer?: string | null
          vote_explainer_generated_at?: string | null
          vote_explainer_model?: string | null
          vote_tally?: string | null
        }
        Update: {
          agenda_item_id?: string
          created_at?: string
          id?: string
          motion_text?: string
          motion_type?: string
          moved_by?: string | null
          resolution_number?: string | null
          result?: string
          seconded_by?: string | null
          sequence_number?: number
          source?: string | null
          vote_explainer?: string | null
          vote_explainer_generated_at?: string | null
          vote_explainer_model?: string | null
          vote_tally?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "motions_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "motions_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
        ]
      }
      motions_embeddings: {
        Row: {
          embedding: unknown
          embedding_generated_at: string
          embedding_model: string
          id: string
        }
        Insert: {
          embedding: unknown
          embedding_generated_at?: string
          embedding_model: string
          id: string
        }
        Update: {
          embedding?: unknown
          embedding_generated_at?: string
          embedding_model?: string
          id?: string
        }
        Relationships: [
          {
            foreignKeyName: "motions_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "motions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "motions_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "v_split_votes"
            referencedColumns: ["motion_id"]
          },
        ]
      }
      neighborhood_councils: {
        Row: {
          city_fips: string
          city_page_id: number | null
          city_page_url: string | null
          contact_email: string | null
          created_at: string | null
          document_center_path: string | null
          geojson_codes: number[]
          id: string
          is_active: boolean
          meeting_location: string | null
          meeting_schedule: string | null
          meeting_time: string | null
          name: string
          nc_type: string
          notes: string | null
          president: string | null
          short_name: string | null
          updated_at: string | null
          vice_president: string | null
        }
        Insert: {
          city_fips?: string
          city_page_id?: number | null
          city_page_url?: string | null
          contact_email?: string | null
          created_at?: string | null
          document_center_path?: string | null
          geojson_codes?: number[]
          id?: string
          is_active?: boolean
          meeting_location?: string | null
          meeting_schedule?: string | null
          meeting_time?: string | null
          name: string
          nc_type?: string
          notes?: string | null
          president?: string | null
          short_name?: string | null
          updated_at?: string | null
          vice_president?: string | null
        }
        Update: {
          city_fips?: string
          city_page_id?: number | null
          city_page_url?: string | null
          contact_email?: string | null
          created_at?: string | null
          document_center_path?: string | null
          geojson_codes?: number[]
          id?: string
          is_active?: boolean
          meeting_location?: string | null
          meeting_schedule?: string | null
          meeting_time?: string | null
          name?: string
          nc_type?: string
          notes?: string | null
          president?: string | null
          short_name?: string | null
          updated_at?: string | null
          vice_president?: string | null
        }
        Relationships: []
      }
      nextrequest_documents: {
        Row: {
          created_at: string
          document_id: string | null
          download_url: string | null
          extracted_text: string | null
          extraction_metadata: Json
          extraction_status: string
          file_size_bytes: number | null
          file_type: string | null
          filename: string | null
          has_redactions: boolean | null
          id: string
          page_count: number | null
          released_date: string | null
          request_id: string
          source_document_id: number | null
          source_removed_at: string | null
        }
        Insert: {
          created_at?: string
          document_id?: string | null
          download_url?: string | null
          extracted_text?: string | null
          extraction_metadata?: Json
          extraction_status?: string
          file_size_bytes?: number | null
          file_type?: string | null
          filename?: string | null
          has_redactions?: boolean | null
          id?: string
          page_count?: number | null
          released_date?: string | null
          request_id: string
          source_document_id?: number | null
          source_removed_at?: string | null
        }
        Update: {
          created_at?: string
          document_id?: string | null
          download_url?: string | null
          extracted_text?: string | null
          extraction_metadata?: Json
          extraction_status?: string
          file_size_bytes?: number | null
          file_type?: string | null
          filename?: string | null
          has_redactions?: boolean | null
          id?: string
          page_count?: number | null
          released_date?: string | null
          request_id?: string
          source_document_id?: number | null
          source_removed_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "nextrequest_documents_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "nextrequest_documents_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "nextrequest_requests"
            referencedColumns: ["id"]
          },
        ]
      }
      nextrequest_requests: {
        Row: {
          city_fips: string
          closed_date: string | null
          created_at: string
          days_to_close: number | null
          department: string | null
          document_count: number | null
          due_date: string | null
          id: string
          metadata: Json
          portal_url: string | null
          request_number: string
          request_text: string
          requester_name: string | null
          source_removed_at: string | null
          status: string
          submitted_date: string | null
          updated_at: string
        }
        Insert: {
          city_fips: string
          closed_date?: string | null
          created_at?: string
          days_to_close?: number | null
          department?: string | null
          document_count?: number | null
          due_date?: string | null
          id?: string
          metadata?: Json
          portal_url?: string | null
          request_number: string
          request_text: string
          requester_name?: string | null
          source_removed_at?: string | null
          status: string
          submitted_date?: string | null
          updated_at?: string
        }
        Update: {
          city_fips?: string
          closed_date?: string | null
          created_at?: string
          days_to_close?: number | null
          department?: string | null
          document_count?: number | null
          due_date?: string | null
          id?: string
          metadata?: Json
          portal_url?: string | null
          request_number?: string
          request_text?: string
          requester_name?: string | null
          source_removed_at?: string | null
          status?: string
          submitted_date?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "nextrequest_requests_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      officials: {
        Row: {
          bio_factual: Json | null
          bio_generated_at: string | null
          bio_model: string | null
          bio_summary: string | null
          bio_summary_provenance: Json | null
          city_fips: string
          created_at: string
          email: string | null
          id: string
          is_current: boolean
          name: string
          normalized_name: string
          party_affiliation: string | null
          phone: string | null
          role: string
          seat: string | null
          term_end: string | null
          term_start: string | null
        }
        Insert: {
          bio_factual?: Json | null
          bio_generated_at?: string | null
          bio_model?: string | null
          bio_summary?: string | null
          bio_summary_provenance?: Json | null
          city_fips: string
          created_at?: string
          email?: string | null
          id?: string
          is_current?: boolean
          name: string
          normalized_name: string
          party_affiliation?: string | null
          phone?: string | null
          role: string
          seat?: string | null
          term_end?: string | null
          term_start?: string | null
        }
        Update: {
          bio_factual?: Json | null
          bio_generated_at?: string | null
          bio_model?: string | null
          bio_summary?: string | null
          bio_summary_provenance?: Json | null
          city_fips?: string
          created_at?: string
          email?: string | null
          id?: string
          is_current?: boolean
          name?: string
          normalized_name?: string
          party_affiliation?: string | null
          phone?: string | null
          role?: string
          seat?: string | null
          term_end?: string | null
          term_start?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "officials_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      officials_embeddings: {
        Row: {
          embedding: unknown
          embedding_generated_at: string
          embedding_model: string
          id: string
        }
        Insert: {
          embedding: unknown
          embedding_generated_at?: string
          embedding_model: string
          id: string
        }
        Update: {
          embedding?: unknown
          embedding_generated_at?: string
          embedding_model?: string
          id?: string
        }
        Relationships: [
          {
            foreignKeyName: "officials_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "officials_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "officials_embeddings_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      opencorporates_api_usage: {
        Row: {
          called_at: string
          endpoint: string
          id: string
          query_params: Json | null
          response_status: number
        }
        Insert: {
          called_at?: string
          endpoint: string
          id?: string
          query_params?: Json | null
          response_status: number
        }
        Update: {
          called_at?: string
          endpoint?: string
          id?: string
          query_params?: Json | null
          response_status?: number
        }
        Relationships: []
      }
      operator_config: {
        Row: {
          city_fips: string
          evidence: Json
          financial: Json
          id: string
          publication: Json
          quality: Json
          temporal: Json
          updated_at: string
          updated_by: string
        }
        Insert: {
          city_fips: string
          evidence?: Json
          financial?: Json
          id?: string
          publication?: Json
          quality?: Json
          temporal?: Json
          updated_at?: string
          updated_by?: string
        }
        Update: {
          city_fips?: string
          evidence?: Json
          financial?: Json
          id?: string
          publication?: Json
          quality?: Json
          temporal?: Json
          updated_at?: string
          updated_by?: string
        }
        Relationships: []
      }
      organizations: {
        Row: {
          city_fips: string
          created_at: string
          entity_number: string | null
          entity_type: string | null
          formation_date: string | null
          id: string
          jurisdiction: string | null
          metadata: Json
          name: string
          normalized_name: string
          registered_agent: string | null
          source: string
          source_updated_at: string | null
          source_url: string | null
          status: string | null
          updated_at: string
        }
        Insert: {
          city_fips: string
          created_at?: string
          entity_number?: string | null
          entity_type?: string | null
          formation_date?: string | null
          id?: string
          jurisdiction?: string | null
          metadata?: Json
          name: string
          normalized_name: string
          registered_agent?: string | null
          source: string
          source_updated_at?: string | null
          source_url?: string | null
          status?: string | null
          updated_at?: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          entity_number?: string | null
          entity_type?: string | null
          formation_date?: string | null
          id?: string
          jurisdiction?: string | null
          metadata?: Json
          name?: string
          normalized_name?: string
          registered_agent?: string | null
          source?: string
          source_updated_at?: string | null
          source_url?: string | null
          status?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "organizations_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      paper_filing_zero_results: {
        Row: {
          city_fips: string
          committee: string
          confidence_score: number
          extracted_at: string
          extraction_method: string
          extraction_model: string
          filing_id: string
          form_type: string
          result_kind: string
          source_tier: number
          source_url: string
        }
        Insert: {
          city_fips?: string
          committee: string
          confidence_score: number
          extracted_at?: string
          extraction_method: string
          extraction_model: string
          filing_id: string
          form_type: string
          result_kind: string
          source_tier?: number
          source_url: string
        }
        Update: {
          city_fips?: string
          committee?: string
          confidence_score?: number
          extracted_at?: string
          extraction_method?: string
          extraction_model?: string
          filing_id?: string
          form_type?: string
          result_kind?: string
          source_tier?: number
          source_url?: string
        }
        Relationships: []
      }
      pb_class_specs: {
        Row: {
          city_fips: string
          class_code: string | null
          definition: string | null
          department: string | null
          duties: string | null
          id: string
          ingested_at: string | null
          neogov_spec_id: string | null
          qualifications: string | null
          salary_max: number | null
          salary_min: number | null
          salary_range: string | null
          salary_type: string | null
          source_url: string
          title: string
        }
        Insert: {
          city_fips?: string
          class_code?: string | null
          definition?: string | null
          department?: string | null
          duties?: string | null
          id?: string
          ingested_at?: string | null
          neogov_spec_id?: string | null
          qualifications?: string | null
          salary_max?: number | null
          salary_min?: number | null
          salary_range?: string | null
          salary_type?: string | null
          source_url: string
          title: string
        }
        Update: {
          city_fips?: string
          class_code?: string | null
          definition?: string | null
          department?: string | null
          duties?: string | null
          id?: string
          ingested_at?: string | null
          neogov_spec_id?: string | null
          qualifications?: string | null
          salary_max?: number | null
          salary_min?: number | null
          salary_range?: string | null
          salary_type?: string | null
          source_url?: string
          title?: string
        }
        Relationships: []
      }
      pb_classification_actions: {
        Row: {
          action_date: string
          action_type: string
          agenda_item_id: string | null
          city_fips: string
          classification_title: string
          created_at: string | null
          days_to_posting: number | null
          department: string | null
          id: string
          meeting_id: string | null
          notes: string | null
          posting_found: boolean | null
          posting_id: string | null
          vote_result: string | null
        }
        Insert: {
          action_date: string
          action_type: string
          agenda_item_id?: string | null
          city_fips?: string
          classification_title: string
          created_at?: string | null
          days_to_posting?: number | null
          department?: string | null
          id?: string
          meeting_id?: string | null
          notes?: string | null
          posting_found?: boolean | null
          posting_id?: string | null
          vote_result?: string | null
        }
        Update: {
          action_date?: string
          action_type?: string
          agenda_item_id?: string | null
          city_fips?: string
          classification_title?: string
          created_at?: string | null
          days_to_posting?: number | null
          department?: string | null
          id?: string
          meeting_id?: string | null
          notes?: string | null
          posting_found?: boolean | null
          posting_id?: string | null
          vote_result?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "pb_classification_actions_posting_id_fkey"
            columns: ["posting_id"]
            isOneToOne: false
            referencedRelation: "pb_job_postings"
            referencedColumns: ["id"]
          },
        ]
      }
      pb_employee_compensation: {
        Row: {
          benefits: number | null
          city_fips: string
          department: string | null
          employee_name: string
          id: string
          ingested_at: string | null
          job_title: string
          other_pay: number | null
          overtime_pay: number | null
          pension_debt: number | null
          regular_pay: number | null
          source_url: string
          total_compensation: number | null
          total_pay: number | null
          year: number
        }
        Insert: {
          benefits?: number | null
          city_fips?: string
          department?: string | null
          employee_name: string
          id?: string
          ingested_at?: string | null
          job_title: string
          other_pay?: number | null
          overtime_pay?: number | null
          pension_debt?: number | null
          regular_pay?: number | null
          source_url: string
          total_compensation?: number | null
          total_pay?: number | null
          year: number
        }
        Update: {
          benefits?: number | null
          city_fips?: string
          department?: string | null
          employee_name?: string
          id?: string
          ingested_at?: string | null
          job_title?: string
          other_pay?: number | null
          overtime_pay?: number | null
          pension_debt?: number | null
          regular_pay?: number | null
          source_url?: string
          total_compensation?: number | null
          total_pay?: number | null
          year?: number
        }
        Relationships: []
      }
      pb_job_postings: {
        Row: {
          city_fips: string
          classification: string | null
          closing_date: string | null
          department: string | null
          exempt_status: string | null
          id: string
          ingested_at: string | null
          is_promotional: boolean | null
          neogov_id: string | null
          posted_date: string | null
          raw_description: string | null
          salary_max: number | null
          salary_min: number | null
          salary_type: string | null
          source_url: string
          status: string | null
          title: string
        }
        Insert: {
          city_fips?: string
          classification?: string | null
          closing_date?: string | null
          department?: string | null
          exempt_status?: string | null
          id?: string
          ingested_at?: string | null
          is_promotional?: boolean | null
          neogov_id?: string | null
          posted_date?: string | null
          raw_description?: string | null
          salary_max?: number | null
          salary_min?: number | null
          salary_type?: string | null
          source_url: string
          status?: string | null
          title: string
        }
        Update: {
          city_fips?: string
          classification?: string | null
          closing_date?: string | null
          department?: string | null
          exempt_status?: string | null
          id?: string
          ingested_at?: string | null
          is_promotional?: boolean | null
          neogov_id?: string | null
          posted_date?: string | null
          raw_description?: string | null
          salary_max?: number | null
          salary_min?: number | null
          salary_type?: string | null
          source_url?: string
          status?: string | null
          title?: string
        }
        Relationships: []
      }
      pb_new_employees: {
        Row: {
          city_fips: string
          department: string | null
          employee_name: string
          employment_type: string | null
          extracted_at: string | null
          id: string
          job_title: string
          meeting_date: string
          meeting_id: string | null
          payroll_match: boolean | null
          posting_id: string | null
          report_month: string | null
          source_transcript: string | null
        }
        Insert: {
          city_fips?: string
          department?: string | null
          employee_name: string
          employment_type?: string | null
          extracted_at?: string | null
          id?: string
          job_title: string
          meeting_date: string
          meeting_id?: string | null
          payroll_match?: boolean | null
          posting_id?: string | null
          report_month?: string | null
          source_transcript?: string | null
        }
        Update: {
          city_fips?: string
          department?: string | null
          employee_name?: string
          employment_type?: string | null
          extracted_at?: string | null
          id?: string
          job_title?: string
          meeting_date?: string
          meeting_id?: string | null
          payroll_match?: boolean | null
          posting_id?: string | null
          report_month?: string | null
          source_transcript?: string | null
        }
        Relationships: []
      }
      pb_research_log: {
        Row: {
          actioned_date: string | null
          actioned_notes: string | null
          body: string | null
          city_fips: string
          core_values: string[]
          created_at: string | null
          evidence: Json
          finding_type: string
          id: string
          lever: string | null
          priority: string
          status: string
          tags: string[]
          title: string
          updated_at: string | null
        }
        Insert: {
          actioned_date?: string | null
          actioned_notes?: string | null
          body?: string | null
          city_fips?: string
          core_values?: string[]
          created_at?: string | null
          evidence?: Json
          finding_type?: string
          id?: string
          lever?: string | null
          priority?: string
          status?: string
          tags?: string[]
          title: string
          updated_at?: string | null
        }
        Update: {
          actioned_date?: string | null
          actioned_notes?: string | null
          body?: string | null
          city_fips?: string
          core_values?: string[]
          created_at?: string | null
          evidence?: Json
          finding_type?: string
          id?: string
          lever?: string | null
          priority?: string
          status?: string
          tags?: string[]
          title?: string
          updated_at?: string | null
        }
        Relationships: []
      }
      pending_decisions: {
        Row: {
          city_fips: string
          created_at: string
          decision_type: string
          dedup_key: string | null
          description: string
          entity_id: string | null
          entity_type: string | null
          evidence: Json | null
          id: string
          link: string | null
          resolution_note: string | null
          resolved_at: string | null
          resolved_by: string | null
          severity: string
          source: string
          status: string
          title: string
          updated_at: string
        }
        Insert: {
          city_fips: string
          created_at?: string
          decision_type: string
          dedup_key?: string | null
          description: string
          entity_id?: string | null
          entity_type?: string | null
          evidence?: Json | null
          id?: string
          link?: string | null
          resolution_note?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          severity?: string
          source: string
          status?: string
          title: string
          updated_at?: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          decision_type?: string
          dedup_key?: string | null
          description?: string
          entity_id?: string | null
          entity_type?: string | null
          evidence?: Json | null
          id?: string
          link?: string | null
          resolution_note?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          severity?: string
          source?: string
          status?: string
          title?: string
          updated_at?: string
        }
        Relationships: []
      }
      pipeline_journal: {
        Row: {
          city_fips: string
          created_at: string
          description: string
          entry_type: string
          id: string
          metrics: Json | null
          session_id: string
          target_artifact: string | null
          zone: string
        }
        Insert: {
          city_fips: string
          created_at?: string
          description: string
          entry_type: string
          id?: string
          metrics?: Json | null
          session_id: string
          target_artifact?: string | null
          zone?: string
        }
        Update: {
          city_fips?: string
          created_at?: string
          description?: string
          entry_type?: string
          id?: string
          metrics?: Json | null
          session_id?: string
          target_artifact?: string | null
          zone?: string
        }
        Relationships: []
      }
      public_comments: {
        Row: {
          agenda_item_id: string | null
          city_fips: string | null
          comment_type: string
          confidence: number | null
          created_at: string
          extracted_at: string | null
          id: string
          meeting_id: string
          method: string
          name_confidence: string | null
          source: string | null
          speaker_name: string
          submitted_by_system: boolean
          summary: string | null
        }
        Insert: {
          agenda_item_id?: string | null
          city_fips?: string | null
          comment_type?: string
          confidence?: number | null
          created_at?: string
          extracted_at?: string | null
          id?: string
          meeting_id: string
          method: string
          name_confidence?: string | null
          source?: string | null
          speaker_name: string
          submitted_by_system?: boolean
          summary?: string | null
        }
        Update: {
          agenda_item_id?: string | null
          city_fips?: string | null
          comment_type?: string
          confidence?: number | null
          created_at?: string
          extracted_at?: string | null
          id?: string
          meeting_id?: string
          method?: string
          name_confidence?: string | null
          source?: string | null
          speaker_name?: string
          submitted_by_system?: boolean
          summary?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "public_comments_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "agenda_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "public_comments_agenda_item_id_fkey"
            columns: ["agenda_item_id"]
            isOneToOne: false
            referencedRelation: "v_staff_agenda_context"
            referencedColumns: ["agenda_item_id"]
          },
          {
            foreignKeyName: "public_comments_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      rate_limit_buckets: {
        Row: {
          bucket_key: string
          count: number
          window_start: string
        }
        Insert: {
          bucket_key: string
          count?: number
          window_start: string
        }
        Update: {
          bucket_key?: string
          count?: number
          window_start?: string
        }
        Relationships: []
      }
      scan_runs: {
        Row: {
          city_fips: string
          clean_items_count: number | null
          completed_at: string | null
          contributions_count: number | null
          contributions_sources: Json | null
          created_at: string
          data_cutoff_date: string | null
          enriched_items_count: number | null
          error_message: string | null
          execution_time_seconds: number | null
          flags_by_tier: Json | null
          flags_found: number
          form700_count: number | null
          id: string
          meeting_id: string | null
          metadata: Json
          model_version: string | null
          pipeline_run_id: string | null
          prompt_version: string | null
          scan_mode: string
          scanner_version: string | null
          status: string
          triggered_by: string | null
        }
        Insert: {
          city_fips: string
          clean_items_count?: number | null
          completed_at?: string | null
          contributions_count?: number | null
          contributions_sources?: Json | null
          created_at?: string
          data_cutoff_date?: string | null
          enriched_items_count?: number | null
          error_message?: string | null
          execution_time_seconds?: number | null
          flags_by_tier?: Json | null
          flags_found?: number
          form700_count?: number | null
          id?: string
          meeting_id?: string | null
          metadata?: Json
          model_version?: string | null
          pipeline_run_id?: string | null
          prompt_version?: string | null
          scan_mode: string
          scanner_version?: string | null
          status?: string
          triggered_by?: string | null
        }
        Update: {
          city_fips?: string
          clean_items_count?: number | null
          completed_at?: string | null
          contributions_count?: number | null
          contributions_sources?: Json | null
          created_at?: string
          data_cutoff_date?: string | null
          enriched_items_count?: number | null
          error_message?: string | null
          execution_time_seconds?: number | null
          flags_by_tier?: Json | null
          flags_found?: number
          form700_count?: number | null
          id?: string
          meeting_id?: string | null
          metadata?: Json
          model_version?: string | null
          pipeline_run_id?: string | null
          prompt_version?: string | null
          scan_mode?: string
          scanner_version?: string | null
          status?: string
          triggered_by?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "scan_runs_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "scan_runs_meeting_id_fkey"
            columns: ["meeting_id"]
            isOneToOne: false
            referencedRelation: "meetings"
            referencedColumns: ["id"]
          },
        ]
      }
      search_queries: {
        Row: {
          city_fips: string
          client_hash: string | null
          created_at: string
          id: string
          query_text: string
          result_count: number
          result_type_filter: string | null
          search_mode: string
        }
        Insert: {
          city_fips?: string
          client_hash?: string | null
          created_at?: string
          id?: string
          query_text: string
          result_count?: number
          result_type_filter?: string | null
          search_mode?: string
        }
        Update: {
          city_fips?: string
          client_hash?: string | null
          created_at?: string
          id?: string
          query_text?: string
          result_count?: number
          result_type_filter?: string | null
          search_mode?: string
        }
        Relationships: []
      }
      source_change_jobs: {
        Row: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }
        Insert: {
          attempt_count?: number
          base_completed_at?: string | null
          change_id: string
          city_fips?: string
          completed_at?: string | null
          created_at?: string
          dispatch_generation?: number
          dispatched_at?: string | null
          fingerprint: Json
          last_error?: string | null
          lease_expires_at?: string | null
          max_attempts?: number
          next_attempt_at?: string
          pipeline_run_id?: string | null
          source: string
          started_at?: string | null
          status?: string
          updated_at?: string
          watcher_source: string
        }
        Update: {
          attempt_count?: number
          base_completed_at?: string | null
          change_id?: string
          city_fips?: string
          completed_at?: string | null
          created_at?: string
          dispatch_generation?: number
          dispatched_at?: string | null
          fingerprint?: Json
          last_error?: string | null
          lease_expires_at?: string | null
          max_attempts?: number
          next_attempt_at?: string
          pipeline_run_id?: string | null
          source?: string
          started_at?: string | null
          status?: string
          updated_at?: string
          watcher_source?: string
        }
        Relationships: [
          {
            foreignKeyName: "source_change_jobs_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      source_watch_state: {
        Row: {
          city_fips: string
          fingerprint: Json
          last_changed_at: string | null
          last_checked_at: string | null
          source: string
          updated_at: string | null
        }
        Insert: {
          city_fips?: string
          fingerprint?: Json
          last_changed_at?: string | null
          last_checked_at?: string | null
          source: string
          updated_at?: string | null
        }
        Update: {
          city_fips?: string
          fingerprint?: Json
          last_changed_at?: string | null
          last_checked_at?: string | null
          source?: string
          updated_at?: string | null
        }
        Relationships: []
      }
      subscription_activations: {
        Row: {
          acquisition_surface: string
          activation_at: string
          activation_kind: string
          city_fips: string
          id: string
          recorded_at: string
          subscriber_id: string
        }
        Insert: {
          acquisition_surface: string
          activation_at: string
          activation_kind: string
          city_fips?: string
          id: string
          recorded_at?: string
          subscriber_id: string
        }
        Update: {
          acquisition_surface?: string
          activation_at?: string
          activation_kind?: string
          city_fips?: string
          id?: string
          recorded_at?: string
          subscriber_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "subscription_activations_subscriber_id_fkey"
            columns: ["subscriber_id"]
            isOneToOne: false
            referencedRelation: "email_subscribers"
            referencedColumns: ["id"]
          },
        ]
      }
      topics: {
        Row: {
          city_fips: string
          color_classes: string | null
          created_at: string
          description: string | null
          id: string
          keywords: string[]
          merged_into_id: string | null
          name: string
          primary_category: string | null
          slug: string
          status: string
          updated_at: string
        }
        Insert: {
          city_fips?: string
          color_classes?: string | null
          created_at?: string
          description?: string | null
          id?: string
          keywords?: string[]
          merged_into_id?: string | null
          name: string
          primary_category?: string | null
          slug: string
          status?: string
          updated_at?: string
        }
        Update: {
          city_fips?: string
          color_classes?: string | null
          created_at?: string
          description?: string | null
          id?: string
          keywords?: string[]
          merged_into_id?: string | null
          name?: string
          primary_category?: string | null
          slug?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "topics_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "topics"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "topics_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "v_topic_stats"
            referencedColumns: ["id"]
          },
        ]
      }
      user_feedback: {
        Row: {
          action_entity_id: string | null
          action_taken: string | null
          city_fips: string
          conflict_nature: string | null
          created_at: string
          current_value: string | null
          description: string | null
          entity_id: string | null
          entity_type: string | null
          evidence_text: string | null
          evidence_url: string | null
          feedback_type: string
          field_name: string | null
          flag_verdict: string | null
          id: string
          is_anonymous: boolean
          moderator_notes: string | null
          official_name: string | null
          page_url: string | null
          reviewed_at: string | null
          reviewed_by: string | null
          session_id: string | null
          status: string
          submitter_email: string | null
          submitter_name: string | null
          suggested_value: string | null
          updated_at: string
        }
        Insert: {
          action_entity_id?: string | null
          action_taken?: string | null
          city_fips: string
          conflict_nature?: string | null
          created_at?: string
          current_value?: string | null
          description?: string | null
          entity_id?: string | null
          entity_type?: string | null
          evidence_text?: string | null
          evidence_url?: string | null
          feedback_type: string
          field_name?: string | null
          flag_verdict?: string | null
          id?: string
          is_anonymous?: boolean
          moderator_notes?: string | null
          official_name?: string | null
          page_url?: string | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          session_id?: string | null
          status?: string
          submitter_email?: string | null
          submitter_name?: string | null
          suggested_value?: string | null
          updated_at?: string
        }
        Update: {
          action_entity_id?: string | null
          action_taken?: string | null
          city_fips?: string
          conflict_nature?: string | null
          created_at?: string
          current_value?: string | null
          description?: string | null
          entity_id?: string | null
          entity_type?: string | null
          evidence_text?: string | null
          evidence_url?: string | null
          feedback_type?: string
          field_name?: string | null
          flag_verdict?: string | null
          id?: string
          is_anonymous?: boolean
          moderator_notes?: string | null
          official_name?: string | null
          page_url?: string | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          session_id?: string | null
          status?: string
          submitter_email?: string | null
          submitter_name?: string | null
          suggested_value?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_feedback_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      votes: {
        Row: {
          id: string
          motion_id: string
          official_id: string | null
          official_name: string
          official_role: string | null
          source: string | null
          vote_choice: string
        }
        Insert: {
          id?: string
          motion_id: string
          official_id?: string | null
          official_name: string
          official_role?: string | null
          source?: string | null
          vote_choice: string
        }
        Update: {
          id?: string
          motion_id?: string
          official_id?: string | null
          official_name?: string
          official_role?: string | null
          source?: string | null
          vote_choice?: string
        }
        Relationships: [
          {
            foreignKeyName: "votes_motion_id_fkey"
            columns: ["motion_id"]
            isOneToOne: false
            referencedRelation: "motions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "votes_motion_id_fkey"
            columns: ["motion_id"]
            isOneToOne: false
            referencedRelation: "v_split_votes"
            referencedColumns: ["motion_id"]
          },
          {
            foreignKeyName: "votes_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "votes_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "votes_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
    }
    Views: {
      donor_context: {
        Row: {
          avg_contribution: number | null
          city_fips: string | null
          contribution_count: number | null
          contribution_span_days: number | null
          distinct_recipients: number | null
          donor_id: string | null
          donor_name: string | null
          employer: string | null
          employer_network_size: number | null
          first_contribution: string | null
          last_contribution: string | null
          max_contribution: number | null
          min_contribution: number | null
          normalized_employer: string | null
          normalized_name: string | null
          occupation: string | null
          total_contributed: number | null
        }
        Relationships: [
          {
            foreignKeyName: "donors_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_appointment_network: {
        Row: {
          appointed_by: string | null
          appointing_official_id: string | null
          appointing_official_name: string | null
          city_fips: string | null
          commission_name: string | null
          commission_type: string | null
          commissioner_name: string | null
          is_current: boolean | null
          role: string | null
          source: string | null
          term_end: string | null
          term_start: string | null
        }
        Relationships: [
          {
            foreignKeyName: "commission_members_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_behested_by_official: {
        Row: {
          city_fips: string | null
          earliest_payment: string | null
          latest_payment: string | null
          official_id: string | null
          official_name: string | null
          payment_count: number | null
          total_amount: number | null
          unique_payees: number | null
          unique_payors: number | null
        }
        Relationships: [
          {
            foreignKeyName: "behested_payments_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "behested_payments_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      v_body_meeting_counts: {
        Row: {
          body_id: string | null
          body_name: string | null
          body_type: string | null
          city_fips: string | null
          first_meeting: string | null
          is_active: boolean | null
          last_meeting: string | null
          meeting_count: number | null
          short_name: string | null
        }
        Relationships: [
          {
            foreignKeyName: "bodies_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_body_roster: {
        Row: {
          body_id: string | null
          body_name: string | null
          body_type: string | null
          city_fips: string | null
          is_current: boolean | null
          member_id: string | null
          member_name: string | null
          normalized_name: string | null
          role: string | null
          source_table: string | null
          term_end: string | null
          term_start: string | null
        }
        Relationships: []
      }
      v_code_enforcement_summary: {
        Row: {
          avg_days_to_close: number | null
          case_type: string | null
          city_fips: string | null
          closed_cases: number | null
          total_cases: number | null
          year: number | null
        }
        Relationships: [
          {
            foreignKeyName: "city_code_cases_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_commission_staleness: {
        Row: {
          city_fips: string | null
          commission_id: string | null
          commission_name: string | null
          last_website_scrape: string | null
          max_days_stale: number | null
          oldest_stale_since: string | null
          stale_member_names: string[] | null
          stale_members: number | null
          total_current_members: number | null
        }
        Relationships: [
          {
            foreignKeyName: "commissions_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_court_entity_summary: {
        Row: {
          avg_confidence: number | null
          case_count: number | null
          case_types: string[] | null
          city_fips: string | null
          donor_id: string | null
          earliest_case: string | null
          entity_name: string | null
          entity_type: string | null
          false_positive_count: number | null
          latest_case: string | null
          max_confidence: number | null
          official_id: string | null
          party_count: number | null
        }
        Relationships: [
          {
            foreignKeyName: "court_case_matches_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "court_case_matches_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donor_context"
            referencedColumns: ["donor_id"]
          },
          {
            foreignKeyName: "court_case_matches_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "court_case_matches_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      v_donor_vote_crossref: {
        Row: {
          amount: number | null
          candidate_name: string | null
          city_fips: string | null
          committee_name: string | null
          contribution_date: string | null
          donor_employer: string | null
          donor_name: string | null
          financial_amount: string | null
          item_number: string | null
          item_title: string | null
          meeting_date: string | null
          official_name: string | null
          vote_choice: string | null
        }
        Relationships: [
          {
            foreignKeyName: "contributions_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_entity_connections: {
        Row: {
          city_fips: string | null
          confidence: number | null
          donor_id: string | null
          effective_date: string | null
          entity_number: string | null
          entity_type: string | null
          normalized_person_name: string | null
          official_id: string | null
          org_source: string | null
          org_status: string | null
          organization_name: string | null
          person_name: string | null
          role: string | null
          role_detail: string | null
        }
        Relationships: [
          {
            foreignKeyName: "entity_links_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
          {
            foreignKeyName: "entity_links_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donor_context"
            referencedColumns: ["donor_id"]
          },
          {
            foreignKeyName: "entity_links_donor_id_fkey"
            columns: ["donor_id"]
            isOneToOne: false
            referencedRelation: "donors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "officials"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_appointment_network"
            referencedColumns: ["appointing_official_id"]
          },
          {
            foreignKeyName: "entity_links_official_id_fkey"
            columns: ["official_id"]
            isOneToOne: false
            referencedRelation: "v_votes_with_context"
            referencedColumns: ["official_id"]
          },
        ]
      }
      v_feedback_ground_truth: {
        Row: {
          audit_notes: string | null
          conflict_flag_id: string | null
          created_at: string | null
          feedback_id: string | null
          ground_truth: boolean | null
          ground_truth_source: string | null
          scan_run_id: string | null
        }
        Relationships: [
          {
            foreignKeyName: "conflict_flags_scan_run_id_fkey"
            columns: ["scan_run_id"]
            isOneToOne: false
            referencedRelation: "scan_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      v_influence_pattern_summary: {
        Row: {
          avg_confidence: number | null
          city_fips: string | null
          flag_count: number | null
          high_confidence_flags: number | null
          max_confidence: number | null
          medium_confidence_flags: number | null
          meeting_count: number | null
          official_count: number | null
          pattern_id: number | null
          pattern_name: string | null
          sort_order: number | null
        }
        Relationships: [
          {
            foreignKeyName: "conflict_flags_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_license_summary: {
        Row: {
          business_type: string | null
          city_fips: string | null
          status: string | null
          total: number | null
          total_employees: number | null
        }
        Relationships: [
          {
            foreignKeyName: "city_licenses_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_lobbyist_clients: {
        Row: {
          city_fips: string | null
          client_name: string | null
          expiration_date: string | null
          lobbyist_firm: string | null
          lobbyist_name: string | null
          registration_date: string | null
          status: string | null
          topics: string | null
        }
        Insert: {
          city_fips?: string | null
          client_name?: string | null
          expiration_date?: string | null
          lobbyist_firm?: string | null
          lobbyist_name?: string | null
          registration_date?: string | null
          status?: string | null
          topics?: string | null
        }
        Update: {
          city_fips?: string | null
          client_name?: string | null
          expiration_date?: string | null
          lobbyist_firm?: string | null
          lobbyist_name?: string | null
          registration_date?: string | null
          status?: string | null
          topics?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "lobbyist_registrations_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_permit_activity: {
        Row: {
          city_fips: string | null
          finaled: number | null
          issued: number | null
          permit_type: string | null
          total_fees: number | null
          total_job_value: number | null
          total_permits: number | null
          year: number | null
        }
        Relationships: [
          {
            foreignKeyName: "city_permits_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_split_votes: {
        Row: {
          category: string | null
          city_fips: string | null
          item_number: string | null
          item_title: string | null
          meeting_date: string | null
          motion_id: string | null
          motion_type: string | null
          result: string | null
          vote_tally: string | null
        }
        Relationships: [
          {
            foreignKeyName: "meetings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_staff_agenda_context: {
        Row: {
          agenda_item_id: string | null
          annual_salary: number | null
          city_fips: string | null
          dept_head_name: string | null
          dept_head_title: string | null
          employee_department: string | null
          hierarchy_level: number | null
          item_department: string | null
          item_title: string | null
          meeting_date: string | null
        }
        Relationships: [
          {
            foreignKeyName: "meetings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_topic_stats: {
        Row: {
          color_classes: string | null
          first_seen: string | null
          id: string | null
          item_count: number | null
          last_seen: string | null
          name: string | null
          primary_category: string | null
          slug: string | null
          status: string | null
        }
        Relationships: []
      }
      v_vendor_spending_summary: {
        Row: {
          city_fips: string | null
          first_payment: string | null
          fiscal_year: string | null
          last_payment: string | null
          normalized_vendor: string | null
          total_amount: number | null
          transaction_count: number | null
          vendor_name: string | null
        }
        Relationships: [
          {
            foreignKeyName: "city_expenditures_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
      v_votes_with_context: {
        Row: {
          category: string | null
          city_fips: string | null
          financial_amount: string | null
          is_consent_calendar: boolean | null
          item_number: string | null
          item_title: string | null
          meeting_date: string | null
          meeting_type: string | null
          motion_result: string | null
          motion_text: string | null
          motion_type: string | null
          official_id: string | null
          official_name: string | null
          official_role: string | null
          vote_choice: string | null
          vote_tally: string | null
        }
        Relationships: [
          {
            foreignKeyName: "meetings_city_fips_fkey"
            columns: ["city_fips"]
            isOneToOne: false
            referencedRelation: "cities"
            referencedColumns: ["fips_code"]
          },
        ]
      }
    }
    Functions: {
      _search_site_candidates: {
        Args: {
          p_city_fips?: string
          p_limit?: number
          p_offset?: number
          p_query: string
          p_result_type?: string
        }
        Returns: {
          id: string
          metadata: Json
          relevance_score: number
          result_type: string
          snippet: string
          title: string
          url_path: string
        }[]
      }
      check_and_increment_rate_limit: {
        Args: {
          p_bucket_key: string
          p_max_count: number
          p_window_secs: number
        }
        Returns: {
          allowed: boolean
          retry_after_secs: number
        }[]
      }
      claim_due_source_change_jobs: {
        Args: {
          p_change_id?: string
          p_lease_minutes?: number
          p_limit?: number
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      claim_email_delivery: {
        Args: {
          p_content_key: string
          p_delivery_kind: string
          p_lease_minutes?: number
          p_max_attempts?: number
          p_payload_sha256: string
          p_subscriber_id: string
        }
        Returns: {
          delivery_attempt: number
          delivery_claim_token: string
          delivery_disposition: string
          delivery_id: string
        }[]
      }
      claim_source_change_job: {
        Args: {
          p_change_id: string
          p_dispatch_generation: number
          p_lease_minutes?: number
          p_pipeline_run_id?: string
          p_source: string
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      cleanup_rate_limit_buckets: { Args: never; Returns: number }
      complete_email_delivery: {
        Args: {
          p_claim_token: string
          p_delivery_id: string
          p_provider_message_id?: string
        }
        Returns: boolean
      }
      complete_source_change_job: {
        Args: {
          p_change_id: string
          p_dispatch_generation: number
          p_pipeline_run_id: string
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      continue_source_change_job: {
        Args: {
          p_change_id: string
          p_delay_seconds?: number
          p_dispatch_generation: number
          p_pipeline_run_id: string
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      fail_email_delivery: {
        Args: {
          p_claim_token: string
          p_delivery_id: string
          p_error: string
          p_is_ambiguous?: boolean
        }
        Returns: string
      }
      find_similar_items: {
        Args: { p_city_fips?: string; p_item_id: string; p_limit?: number }
        Returns: {
          category: string
          financial_amount: string
          id: string
          item_number: string
          meeting_date: string
          meeting_id: string
          public_comment_count: number
          similarity: number
          summary_headline: string
          title: string
          topic_label: string
          vote_outcome: string
        }[]
      }
      get_category_stats: {
        Args: { p_city_fips?: string }
        Returns: {
          avg_controversy_score: number
          category: string
          item_count: number
          max_controversy_score: number
          percentage_of_agenda: number
          split_vote_count: number
          total_public_comments: number
          unanimous_vote_count: number
          vote_count: number
        }[]
      }
      get_contested_votes: {
        Args: { p_city_fips?: string; p_official_ids?: string[] }
        Returns: {
          category: string
          motion_id: string
          official_id: string
          official_name: string
          vote_choice: string
        }[]
      }
      get_controversial_items: {
        Args: { p_city_fips?: string; p_limit?: number }
        Returns: {
          agenda_item_id: string
          category: string
          controversy_score: number
          item_number: string
          meeting_date: string
          meeting_id: string
          motion_count: number
          public_comment_count: number
          result: string
          title: string
          vote_tally: string
        }[]
      }
      get_divergent_motions_detail: {
        Args: { p_city_fips?: string; p_official_ids?: string[] }
        Returns: {
          agenda_item_id: string
          agenda_item_number: string
          agenda_item_title: string
          category: string
          is_procedural: boolean
          meeting_date: string
          meeting_id: string
          motion_id: string
          motion_result: string
          motion_text: string
          official_id: string
          official_name: string
          topic_label: string
          vote_choice: string
          vote_tally: string
        }[]
      }
      get_meeting_counts: {
        Args: { p_city_fips: string }
        Returns: {
          agenda_item_count: number
          categories: Json
          meeting_id: string
          topic_labels: Json
          vote_count: number
        }[]
      }
      get_meeting_flag_counts: {
        Args: { p_city_fips: string }
        Returns: {
          flags_published: number
          flags_total: number
          items_scanned: number
          meeting_id: string
        }[]
      }
      get_official_voting_record: {
        Args: { p_official_id: string }
        Returns: {
          agenda_item_id: string
          category: string
          has_nay_votes: boolean
          id: string
          is_consent_calendar: boolean
          item_number: string
          item_title: string
          meeting_date: string
          meeting_id: string
          meeting_type: string
          motion_id: string
          motion_result: string
          motion_text: string
          official_name: string
          public_comment_count: number
          topic_label: string
          vote_choice: string
          vote_tally: string
        }[]
      }
      list_public_tables: {
        Args: never
        Returns: {
          table_name: string
        }[]
      }
      mark_source_change_base_completed: {
        Args: {
          p_change_id: string
          p_dispatch_generation: number
          p_pipeline_run_id: string
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      merge_official_pair: {
        Args: { p_dupe_id: string; p_keeper_id: string }
        Returns: undefined
      }
      parse_vote_tally: {
        Args: { tally: string }
        Returns: {
          ayes: number
          nays: number
        }[]
      }
      prune_subscription_activations: { Args: never; Returns: number }
      replace_email_preferences: {
        Args: {
          p_candidates?: string[]
          p_districts?: string[]
          p_subscriber_id: string
          p_topics?: string[]
        }
        Returns: undefined
      }
      reserve_llm_cost: {
        Args: {
          p_caller: string
          p_city_fips: string
          p_event_type?: string
          p_metadata?: Json
          p_model: string
          p_monthly_cap: number
          p_projected_cost: number
          p_reservation_id: string
        }
        Returns: {
          committed_cost: number
          reason: string
          reserved: boolean
        }[]
      }
      retry_source_change_job: {
        Args: {
          p_change_id: string
          p_dispatch_generation: number
          p_error: string
          p_pipeline_run_id?: string
        }
        Returns: {
          attempt_count: number
          base_completed_at: string | null
          change_id: string
          city_fips: string
          completed_at: string | null
          created_at: string
          dispatch_generation: number
          dispatched_at: string | null
          fingerprint: Json
          last_error: string | null
          lease_expires_at: string | null
          max_attempts: number
          next_attempt_at: string
          pipeline_run_id: string | null
          source: string
          started_at: string | null
          status: string
          updated_at: string
          watcher_source: string
        }[]
        SetofOptions: {
          from: "*"
          to: "source_change_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      search_hybrid: {
        Args: {
          p_city_fips?: string
          p_limit?: number
          p_offset?: number
          p_query: string
          p_query_embedding?: string
          p_result_type?: string
        }
        Returns: {
          id: string
          match_type: string
          metadata: Json
          relevance_score: number
          result_type: string
          snippet: string
          title: string
          url_path: string
        }[]
      }
      search_site: {
        Args: {
          p_city_fips?: string
          p_limit?: number
          p_offset?: number
          p_query: string
          p_result_type?: string
        }
        Returns: {
          id: string
          metadata: Json
          relevance_score: number
          result_type: string
          snippet: string
          title: string
          url_path: string
        }[]
      }
      settle_llm_cost_reservation: {
        Args: {
          p_actual_cost: number
          p_input_tokens: number
          p_metadata?: Json
          p_output_tokens?: number
          p_reservation_id: string
        }
        Returns: boolean
      }
      terminalize_retryable_email_delivery: {
        Args: {
          p_delivery_id: string
          p_failure_kind: string
          p_manual_review?: boolean
          p_reason: string
        }
        Returns: boolean
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
