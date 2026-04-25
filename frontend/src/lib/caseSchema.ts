import { z } from 'zod'

/**
 * Schema Zod de validação do formulário de Caso.
 * Espelha o `CaseInput` do backend (types.ts gerado da OpenAPI) mas
 * adiciona validações e mensagens em PT-BR que a API levantaria só no submit.
 */
export const lineSegmentSchema = z.object({
  length: z.number().positive('Comprimento deve ser > 0'),
  w: z.number().positive('Peso submerso deve ser > 0'),
  EA: z.number().positive('EA deve ser > 0'),
  MBL: z.number().positive('MBL deve ser > 0'),
  category: z
    .enum(['Wire', 'StuddedChain', 'StudlessChain', 'Polyester'])
    .nullable()
    .optional(),
  line_type: z.string().nullable().optional(),
  // Metadados (não entram no solver, mas documentam a linha)
  diameter: z.number().positive().nullable().optional(),
  dry_weight: z.number().positive().nullable().optional(),
  modulus: z.number().positive().nullable().optional(),
})

export const boundarySchema = z.object({
  h: z.number().positive("Lâmina d'água deve ser > 0"),
  mode: z.enum(['Tension', 'Range']),
  input_value: z.number().positive('Valor deve ser > 0'),
  startpoint_depth: z.number().min(0).default(0),
  endpoint_grounded: z.boolean().default(true),
})

export const seabedSchema = z.object({
  mu: z.number().min(0, 'Atrito não pode ser negativo').default(0),
})

export const userLimitsSchema = z.object({
  yellow_ratio: z.number().positive().max(1.0),
  red_ratio: z.number().positive().max(1.0),
  broken_ratio: z.number().positive().max(2.0),
})

export const caseInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, 'Nome obrigatório')
      .max(200, 'Máximo 200 caracteres'),
    description: z.string().trim().max(2000).optional().nullable(),
    segments: z
      .array(lineSegmentSchema)
      .min(1, 'Informe ao menos 1 segmento')
      .max(1, 'MVP v1 aceita apenas 1 segmento (multi-segmento virá em v2.1)'),
    boundary: boundarySchema,
    seabed: seabedSchema,
    criteria_profile: z.enum([
      'MVP_Preliminary',
      'API_RP_2SK',
      'DNV_placeholder',
      'UserDefined',
    ]),
    user_defined_limits: userLimitsSchema.optional().nullable(),
  })
  .refine(
    (v) =>
      v.criteria_profile !== 'UserDefined' || v.user_defined_limits != null,
    {
      message: 'Defina limites custom para perfil UserDefined',
      path: ['user_defined_limits'],
    },
  )
  .refine(
    (v) => {
      if (v.criteria_profile !== 'UserDefined' || !v.user_defined_limits) return true
      const { yellow_ratio, red_ratio, broken_ratio } = v.user_defined_limits
      return yellow_ratio < red_ratio && red_ratio < broken_ratio
    },
    {
      message: 'yellow < red < broken',
      path: ['user_defined_limits'],
    },
  )

export type CaseFormValues = z.infer<typeof caseInputSchema>

export const EMPTY_CASE: CaseFormValues = {
  name: '',
  description: '',
  segments: [
    {
      length: 450,
      w: 201.1,
      EA: 3.425e7,
      MBL: 3.78e6,
      category: 'Wire',
      line_type: null,
      diameter: 0.0762,      // 3" ~ wire rope IWRCEIPS default
      dry_weight: 242.3,     // 16.6 lbf/ft
      modulus: 6.76e10,      // 9804 kip/in² — módulo aparente wire
    },
  ],
  boundary: {
    h: 300,
    mode: 'Tension',
    input_value: 785_000,
    startpoint_depth: 0,
    endpoint_grounded: true,
  },
  seabed: { mu: 0.6 },       // default de wire em argila firme (Seção 4.4)
  criteria_profile: 'MVP_Preliminary',
  user_defined_limits: null,
}
