package org.mitre.synthea.export.rif;

import static org.junit.Assert.assertEquals;

import java.util.List;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;
import org.mitre.synthea.TestHelper;
import org.mitre.synthea.world.agents.PayerManager;
import org.mitre.synthea.world.agents.Person;
import org.mitre.synthea.world.concepts.Claim;
import org.mitre.synthea.world.concepts.HealthRecord;
import org.mitre.synthea.world.concepts.HealthRecord.Code;
import org.mitre.synthea.world.concepts.HealthRecord.Encounter;
import org.mitre.synthea.world.concepts.HealthRecord.EncounterType;
import org.mitre.synthea.world.concepts.HealthRecord.Medication;
import org.mitre.synthea.world.geography.Location;

public class RIFExporterTest {

  private RIFExporter rifExporter;

  /**
   * Load test properties and payers once for all tests.
   * @throws Exception if something goes wrong
   */
  @BeforeClass
  public static void setUpClass() throws Exception {
    TestHelper.exportOff();
    TestHelper.loadTestProperties();
    PayerManager.loadPayers(new Location("Massachusetts", null));
  }

  @Before
  public void setUp() {
    rifExporter = new CarrierExporter(BB2RIFExporter.getInstance());
  }

  private Encounter encounterWithAdministeredMed(Person person, Medication[] medOut) {
    HealthRecord record = new HealthRecord(person);
    Encounter encounter = record.encounterStart(0L, EncounterType.OUTPATIENT);
    Medication med = record.medicationAdministration(0L, "999999");
    med.codes.add(new Code("RxNorm", "999999", "Test Drug"));
    med.claim.assignCosts();
    medOut[0] = med;
    return encounter;
  }

  @Test
  public void administeredMedicationAppearsExactlyOnceInBillableItems() {
    Person person = new Person(0L);
    person.attributes.put(Person.BIRTHDATE, 0L);
    person.coverage.setPlanToNoInsurance(0L);
    Medication[] medOut = new Medication[1];
    Encounter encounter = encounterWithAdministeredMed(person, medOut);

    List<Claim.ClaimEntry> items = rifExporter.getBillableProcedureAndMedAdminItems(encounter);

    long medLineCount = items.stream().filter(item -> item.entry == medOut[0]).count();
    assertEquals("an administered medication must produce exactly one billable line item",
        1, medLineCount);
  }
}
