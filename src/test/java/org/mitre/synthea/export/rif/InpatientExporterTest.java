package org.mitre.synthea.export.rif;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.nio.file.Files;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.BeforeClass;
import org.junit.ClassRule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.mitre.synthea.TestHelper;
import org.mitre.synthea.helpers.Config;
import org.mitre.synthea.helpers.SimpleCSV;
import org.mitre.synthea.world.agents.PayerManager;
import org.mitre.synthea.world.agents.Person;
import org.mitre.synthea.world.agents.Provider;
import org.mitre.synthea.world.concepts.HealthRecord;
import org.mitre.synthea.world.concepts.HealthRecord.Code;
import org.mitre.synthea.world.concepts.HealthRecord.Encounter;
import org.mitre.synthea.world.concepts.HealthRecord.EncounterType;
import org.mitre.synthea.world.concepts.HealthRecord.Medication;
import org.mitre.synthea.world.geography.Location;

public class InpatientExporterTest {

  private static final String TEST_BENE_ID = "TEST-INPATIENT-JCODE";

  @ClassRule
  public static TemporaryFolder tempFolder = new TemporaryFolder();

  private static File exportDir;

  /**
   * Global setup for inpatient export tests.
   * @throws Exception if something goes wrong
   */
  @BeforeClass
  public static void setUpExportDir() throws Exception {
    TestHelper.exportOff();
    TestHelper.loadTestProperties();
    PayerManager.loadPayers(new Location("Massachusetts", null));
    Config.set("exporter.bfd.export", "true");
    Config.set("exporter.bfd.require_code_maps", "false");
    exportDir = tempFolder.newFolder();
    Config.set("exporter.baseDirectory", exportDir.toString());
    // rebind the writers so output lands in this test's directory even when the
    // singleton was constructed by an earlier test class
    BB2RIFExporter exporter = BB2RIFExporter.getInstance();
    exporter.rifWriters = exporter.prepareOutputFiles();
  }

  @Test
  public void administeredMedicationGetsJCodeInsteadOfT1502() throws Exception {
    long time = 1600000000000L; // Sep 2020, after the BFD claim cutoff date
    Person person = new Person(0L);
    person.attributes.put(Person.BIRTHDATE, time);
    person.attributes.put(RIFExporter.BB2_BENE_ID, TEST_BENE_ID);
    person.attributes.put(RIFExporter.COVERAGE_START_DATE, 0L);
    person.coverage.setPlanToNoInsurance(time);

    Provider provider = TestHelper.buildMockProvider();
    provider.state = "Massachusetts";
    HealthRecord record = person.record;
    Encounter encounter = record.encounterStart(time, EncounterType.INPATIENT);
    encounter.provider = provider;
    encounter.clinician = provider.clinicianMap.values().iterator().next().get(0);
    encounter.reason = new Code("SNOMED-CT", "44054006", "Type 2 diabetes mellitus");

    // carfilzomib maps to J9047 in rxnorm_hcpcs_map.json
    Medication med = record.medicationAdministration(time, "1302966");
    med.codes.add(new Code("RxNorm", "1302966", "Carfilzomib"));
    med.claim.assignCosts();

    encounter.stop = time + 86400000L; // 1 day stay
    encounter.ended = true;

    InpatientExporter inpatientExporter =
        new InpatientExporter(BB2RIFExporter.getInstance());
    long claimCount = inpatientExporter.export(person, 0L, encounter.stop);
    assertEquals(1, claimCount);

    // Exporter.appendToFile buffers output; flush so the file can be read back
    java.lang.reflect.Method closeOpenFiles =
        org.mitre.synthea.export.Exporter.class.getDeclaredMethod("closeOpenFiles");
    closeOpenFiles.setAccessible(true);
    closeOpenFiles.invoke(null);

    File inpatientFile = exportDir.toPath().resolve("bfd").resolve("inpatient.csv").toFile();
    assertTrue(inpatientFile.exists() && inpatientFile.isFile());
    String csvData = new String(Files.readAllBytes(inpatientFile.toPath()));
    List<LinkedHashMap<String, String>> rows = SimpleCSV.parse(csvData, '|').stream()
        .filter(row -> TEST_BENE_ID.equals(row.get("BENE_ID")))
        .collect(Collectors.toList());
    // one medication line plus the total charge line
    assertEquals(2, rows.size());

    LinkedHashMap<String, String> medLine = rows.get(0);
    assertEquals("administered drug with a J-code mapping should carry its J-code",
        "J9047", medLine.get("HCPCS_CD"));
  }
}
